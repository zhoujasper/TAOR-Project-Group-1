from collections import defaultdict
from ortools.sat.python import cp_model

from data.schema import ComponentType, CourseKind, WeekPattern, Instance
from model.variables import VarSets
from model.utils import is_sectioned, sum_vars, link_or


def add_courses_constraints(model: cp_model.CpModel, inst: Instance, vs: VarSets):
    # All timeslot keys: (timeslot_key_id) -> TimeslotKey object
    key_by_id = inst.timeslot_key_by_id

    # All course components: (course_id, component_id) -> CourseComponent object
    comp_by_id = {(c.id, comp.id): comp for c in inst.courses for comp in c.components}

    # Student counts for weighting enrollment sums
    count_of = {s.id: s.number_students for s in inst.students}

    # All students participation in courses (weighted by number_students):
    # (course_id, year, semester) -> [N_i * take_i terms]
    take_by_ct = defaultdict(list)
    for (sid, cid, y, sem), tv in vs.take.items():
        take_by_ct[(cid, y, sem)].append(count_of[sid] * tv)

    # All student assignments to a timeslot key (weighted by number_students):
    # (course_id, component_id, timeslot_key_id) -> list of N_i * assign_i terms
    assign_by_sec = defaultdict(list)
    for (sid, cid, compid, kid), av in vs.assign.items():
        assign_by_sec[(cid, compid, kid)].append(count_of[sid] * av)

    # Decompose the timeslot_key_id in open vars (timeslot_key_id) -> (year, semester)
    # (course_id, component_id, year, semester) -> [BoolVars for open course components]
    open_by_comp_sem = defaultdict(list)

    # Decompose the timeslot_key_id in open vars (timeslot_key_id) -> (base_id, week_pattern)
    # (course_id, base_id, week_pattern) -> [BoolVars for open course components]
    # NOTE: base_id = (year, semester, day, period)
    open_by_base_wp = defaultdict(list)

    # Collect the above two dicts
    for (cid, compid, kid), ov in vs.open.items():
        k = key_by_id[kid]
        open_by_comp_sem[(cid, compid, k.year, k.semester)].append(ov)
        open_by_base_wp[(cid, k.base_id, k.week_pattern)].append(ov)

    all_years = inst.all_years
    all_semesters = inst.all_semesters


    # ----------------------------------------------------------------------------------------------------------
    # - Each course offered in at most ONE semester, but can be active in multiple years within that same semester
    # - within the chosen semester, the course must have same active status in ALL allowed years 
    #   (forbidden by rules is handled in var creation)
    # ----------------------------------------------------------------------------------------------------------

    # All active vars for a course in a semester (later use)
    # (course_id, semester) -> list of active vars for that course in that semester (across all years)
    sem_ind_map = {}

    for c in inst.courses:
        sem_inds = []
        for sem in all_semesters:
            # Active vars for this course in this semester (across all years)
            act_vars = [vs.active[(c.id, y, sem)] for y in all_years if (c.id, y, sem) in vs.active]

            # If there are no active vars for this course in this semester, skip it.
            if not act_vars:
                continue

            # indicator = 1 if course is offered in this semester in ANY year
            ind = model.new_bool_var(f"sem_active[{c.id},S{sem}]")
            link_or(model, act_vars, ind)

            # Append all indicators for this course across semesters
            sem_inds.append(ind)
            sem_ind_map[(c.id, sem)] = ind
        
        # Each course can be offered in at most one semester
        if sem_inds:
            model.add(sum(sem_inds) <= 1)

        # within the chosen semester, the course must have same active status in ALL allowed years
        # NOTE: For the rules which allow or forbid offering in specific years/semesters, 
        # it is easier to just not create active vars for those year/semester combinations, 
        # so we don't need to add extra constraints here. (we already do this when creating vars)
        for sem in all_semesters:
            act_vars = [vs.active[(c.id, y, sem)] for y in all_years if (c.id, y, sem) in vs.active]
            if len(act_vars) > 1:
                # all active vars in this semester must be equal
                for av in act_vars[1:]:
                    model.add(av == act_vars[0])


    # ----------------------------------------------------------------------------------------------------------
    # Per-semester course offering counts
    # ----------------------------------------------------------------------------------------------------------

    gw_per_sem = inst.rules.global_gateway_per_semester
    opt_per_sem = inst.rules.global_optional_per_semester

    for sem in all_semesters:
        gw = [sem_ind_map[(c.id, sem)] for c in inst.courses if c.kind == CourseKind.MATH_GW and (c.id, sem) in sem_ind_map]
        opt = [sem_ind_map[(c.id, sem)] for c in inst.courses if c.kind == CourseKind.MATH_OP and (c.id, sem) in sem_ind_map]
        if gw:
            model.add(sum(gw) == gw_per_sem)
        if opt:
            model.add(sum(opt) == opt_per_sem)


    # ----------------------------------------------------------------------------------------------------------
    # Each course: open <-> active (consistency and need satisfy our max/min requirements)
    # ----------------------------------------------------------------------------------------------------------
    
    for c in inst.courses:
        for comp in c.components:
            min_sec = comp.number_per_week * comp.sections_min
            max_sec = comp.number_per_week * comp.sections_max
            min_att = comp.sections_min * comp.section_cap_min

            for y in all_years:
                for sem in all_semesters:
                    act_key = (c.id, y, sem)

                    # If no active var for this course in this year/semester, skip it.
                    if act_key not in vs.active:
                        continue

                    # active var for this course in this year/semester
                    act = vs.active[act_key]

                    # get all open vars for this course component in this year/semester
                    olist = open_by_comp_sem.get((c.id, comp.id, y, sem), [])

                    # (=>) If exist course components that are open -> course must be active
                    for ov in olist:
                        model.add_implication(ov, act)

                    # If no course components for this course in this year/semester, then course cannot be active
                    if not olist:
                        if min_sec > 0:
                            model.add(act == 0)
                        continue
                    
                    # (<=) If course is active -> number of open course components must be between min_sec and max_sec
                    s = sum(olist)
                    model.add(s >= min_sec * act)
                    model.add(s <= max_sec * act)

                    # Course active requires at least min_att students taking it
                    if min_att > 0:
                        takes = take_by_ct.get((c.id, y, sem), [])
                        if takes:
                            model.add(sum(takes) >= min_att * act)
                        else:
                            # No student can enroll -> cannot satisfy min attendance
                            model.add(act == 0)


    # ----------------------------------------------------------------------------------------------------------
    # Implied: force active=0 when no student has a take var for this (course, year, semester)
    # ----------------------------------------------------------------------------------------------------------

    for (cid, y, sem), act in vs.active.items():
        if not take_by_ct.get((cid, y, sem)):
            model.add(act == 0)


    # ----------------------------------------------------------------------------------------------------------
    # - For sectioned components: Each open course component must have students assigned to it, and if sectioned, must satisfy section cap constraints
    # - For non-sectioned components: number of students taking the course must satisfy the component cap constraints
    # ----------------------------------------------------------------------------------------------------------

    nonsect_checked = set()
    for (cid, compid, kid), open_var in vs.open.items():
        comp = comp_by_id[(cid, compid)]
        k = key_by_id[kid]

        # For sectioned components: each open slot has its own student assignments
        if is_sectioned(comp):
            assigns = assign_by_sec.get((cid, compid, kid), [])

            # If this section is open -> assigned students must be within [cap_min, cap_max].
            # When not open -> all assigns must be 0.
            if assigns:
                s = sum(assigns)
                model.add(s == 0).only_enforce_if(open_var.Not())
                model.add(s <= comp.section_cap_max).only_enforce_if(open_var)
                model.add(s >= comp.section_cap_min).only_enforce_if(open_var)

        # For non-sectioned components: all open slots in the same (course, component, year, semester)
        # share the same enrollment sum, so one constraint per group suffices (conditioned on active).
        else:
            group_key = (cid, compid, k.year, k.semester)
            if group_key in nonsect_checked:
                continue
            nonsect_checked.add(group_key)

            act = vs.active.get((cid, k.year, k.semester))
            if act is None:
                continue
            takes = take_by_ct.get((cid, k.year, k.semester), [])
            if takes:
                s = sum(takes)
                if comp.section_cap_max < 999:
                    model.add(s <= comp.section_cap_max).only_enforce_if(act)
                if comp.section_cap_min > 0:
                    model.add(s >= comp.section_cap_min).only_enforce_if(act)

    
    # ----------------------------------------------------------------------------------------------------------
    # For a given course, there cannot be internal timetable conflicts between its lectures.
    # Lecture slots: at most 1 per (base_id, week_pattern).
    # ----------------------------------------------------------------------------------------------------------

    # Build open vars grouped by (course_id, base_id, week_pattern, is_workshop)
    open_by_base_wp_type = defaultdict(list)
    for (cid, compid, kid), ov in vs.open.items():
        k = key_by_id[kid]
        comp = comp_by_id[(cid, compid)]
        is_ws = (comp.component_type == ComponentType.WORKSHOP)
        open_by_base_wp_type[(cid, k.base_id, k.week_pattern, is_ws)].append(ov)

    for c in inst.courses:
        bases = {base for (cid, base, _, _) in open_by_base_wp_type if cid == c.id}
        for base in bases:
            for wp_main in [WeekPattern.ALL, WeekPattern.ODD, WeekPattern.EVEN]:
                lec = open_by_base_wp_type.get((c.id, base, wp_main, False), [])

                # Lecture: at most 1
                if lec:
                    model.add(sum(lec) <= 1)

            # Cross week-pattern exclusions (ALL conflicts with ODD/EVEN)
            for wp_pair in [(WeekPattern.ALL, WeekPattern.ODD), (WeekPattern.ALL, WeekPattern.EVEN)]:
                lec_a = open_by_base_wp_type.get((c.id, base, wp_pair[0], False), [])
                lec_b = open_by_base_wp_type.get((c.id, base, wp_pair[1], False), [])

                all_lec = lec_a + lec_b

                if all_lec:
                    model.add(sum(all_lec) <= 1)


    # ----------------------------------------------------------------------------------------------------------
    # Global room-cap hard constraint: on the same timeslot, total open course sections
    # across all courses/components cannot exceed max_concurrent_courses_per_timeslot.
    # ----------------------------------------------------------------------------------------------------------

    max_conc_courses = inst.rules.max_concurrent_courses_per_timeslot
    if max_conc_courses < 999:
        open_by_base_wp = defaultdict(list)
        for (_, _, kid), ov in vs.open.items():
            k = key_by_id[kid]
            open_by_base_wp[(k.base_id, k.week_pattern)].append(ov)

        for _, ovs in open_by_base_wp.items():
            if ovs:
                model.add(sum(ovs) <= max_conc_courses)

        bases = {base for (base, _) in open_by_base_wp.keys()}
        for base in bases:
            for wp_a, wp_b in [
                (WeekPattern.ALL, WeekPattern.ODD),
                (WeekPattern.ALL, WeekPattern.EVEN),
            ]:
                ovs_a = open_by_base_wp.get((base, wp_a), [])
                ovs_b = open_by_base_wp.get((base, wp_b), [])
                ovs_combined = ovs_a + ovs_b
                if ovs_combined:
                    model.add(sum(ovs_combined) <= max_conc_courses)


    # ----------------------------------------------------------------------------------------------------------
    # Course max sessions per day: (Based on real situation) on any physical day, a non-outside course can use at most
    # course_max_slots_per_day distinct periods (across all components).
    # ----------------------------------------------------------------------------------------------------------

    max_per_day = inst.rules.course_max_slots_per_day
    if max_per_day < 999:
        all_days_set = {k.day for k in inst.timeslot_keys_list}
        all_periods_set = {k.period for k in inst.timeslot_keys_list}
        physical_weeks = [
            ("even", {WeekPattern.ALL, WeekPattern.EVEN}),
            ("odd",  {WeekPattern.ALL, WeekPattern.ODD}),
        ]

        for c in inst.courses:
            if c.kind == CourseKind.OUTSIDE:
                continue

            for y in all_years:
                for sem in all_semesters:
                    for d in all_days_set:
                        for pw_label, wps in physical_weeks:
                            period_ovs = defaultdict(list)
                            for comp in c.components:
                                for wp in wps:
                                    for p in all_periods_set:
                                        key_id = f"Y{y}_S{sem}_{wp.value}_D{d}_P{p}"
                                        ov = vs.open.get((c.id, comp.id, key_id))
                                        if ov is not None:
                                            period_ovs[p].append(ov)

                            if len(period_ovs) <= max_per_day:
                                continue

                            indicators = []
                            for p in period_ovs:
                                ovs = period_ovs[p]
                                if len(ovs) == 1:
                                    indicators.append(ovs[0])
                                else:
                                    ind = model.new_bool_var(
                                        f"cday[{c.id},Y{y},S{sem},{pw_label},D{d},P{p}]")
                                    link_or(model, ovs, ind)
                                    indicators.append(ind)

                            model.add(sum(indicators) <= max_per_day)


    # ----------------------------------------------------------------------------------------------------------
    # Lecture max per day: on any physical day, a non-outside course can have at most
    # lecture_max_per_day distinct lecture periods.
    # ----------------------------------------------------------------------------------------------------------

    lec_per_day = inst.rules.lecture_max_per_day
    if lec_per_day < 999:
        all_days_set = {k.day for k in inst.timeslot_keys_list}
        all_periods_set = {k.period for k in inst.timeslot_keys_list}
        physical_weeks = [
            ("even", {WeekPattern.ALL, WeekPattern.EVEN}),
            ("odd",  {WeekPattern.ALL, WeekPattern.ODD}),
        ]

        for c in inst.courses:
            if c.kind == CourseKind.OUTSIDE:
                continue

            lec_comps = [comp for comp in c.components if comp.component_type == ComponentType.LECTURE]
            if not lec_comps:
                continue

            for y in all_years:
                for sem in all_semesters:
                    for d in all_days_set:
                        for pw_label, wps in physical_weeks:
                            period_ovs = defaultdict(list)
                            for comp in lec_comps:
                                for wp in wps:
                                    for p in all_periods_set:
                                        key_id = f"Y{y}_S{sem}_{wp.value}_D{d}_P{p}"
                                        ov = vs.open.get((c.id, comp.id, key_id))
                                        if ov is not None:
                                            period_ovs[p].append(ov)

                            if len(period_ovs) <= lec_per_day:
                                continue

                            indicators = []
                            for p in period_ovs:
                                ovs = period_ovs[p]
                                if len(ovs) == 1:
                                    indicators.append(ovs[0])
                                else:
                                    ind = model.new_bool_var(
                                        f"lecday[{c.id},Y{y},S{sem},{pw_label},D{d},P{p}]")
                                    link_or(model, ovs, ind)
                                    indicators.append(ind)

                            model.add(sum(indicators) <= lec_per_day)


    # ----------------------------------------------------------------------------------------------------------
    # Workshop max per day: on any physical day, a non-outside course can have at most
    # workshop_max_per_day distinct workshop periods.
    # ----------------------------------------------------------------------------------------------------------

    ws_per_day = inst.rules.workshop_max_per_day
    if ws_per_day < 999:
        all_days_set = {k.day for k in inst.timeslot_keys_list}
        all_periods_set = {k.period for k in inst.timeslot_keys_list}
        physical_weeks = [
            ("even", {WeekPattern.ALL, WeekPattern.EVEN}),
            ("odd",  {WeekPattern.ALL, WeekPattern.ODD}),
        ]

        for c in inst.courses:
            if c.kind == CourseKind.OUTSIDE:
                continue

            ws_comps = [comp for comp in c.components if comp.component_type == ComponentType.WORKSHOP]
            if not ws_comps:
                continue

            for y in all_years:
                for sem in all_semesters:
                    for d in all_days_set:
                        for pw_label, wps in physical_weeks:
                            period_ovs = defaultdict(list)
                            for comp in ws_comps:
                                for wp in wps:
                                    for p in all_periods_set:
                                        key_id = f"Y{y}_S{sem}_{wp.value}_D{d}_P{p}"
                                        ov = vs.open.get((c.id, comp.id, key_id))
                                        if ov is not None:
                                            period_ovs[p].append(ov)

                            if len(period_ovs) <= ws_per_day:
                                continue

                            indicators = []
                            for p in period_ovs:
                                ovs = period_ovs[p]
                                if len(ovs) == 1:
                                    indicators.append(ovs[0])
                                else:
                                    ind = model.new_bool_var(
                                        f"wsday[{c.id},Y{y},S{sem},{pw_label},D{d},P{p}]")
                                    link_or(model, ovs, ind)
                                    indicators.append(ind)

                            model.add(sum(indicators) <= ws_per_day)


    # ----------------------------------------------------------------------------------------------------------
    # Workshop-after-lecture: for each non-outside course, every open workshop slot must be
    # AFTER at least one lecture of the same course (earlier day, or same day earlier period).
    # Additionally, on the same day, no lecture may be scheduled at a period >= the workshop.
    # ----------------------------------------------------------------------------------------------------------

    if inst.rules.workshop_after_lecture:
        # Pre-index lecture open vars by (course_id, year, semester, day) -> [(period, ov), ...]
        lec_open_by_day = defaultdict(list)
        for (cid, compid, kid), ov in vs.open.items():
            comp = comp_by_id[(cid, compid)]
            if comp.component_type != ComponentType.LECTURE:
                continue
            k = key_by_id[kid]
            lec_open_by_day[(cid, k.year, k.semester, k.day)].append((k.period, ov))

        for c in inst.courses:
            if c.kind == CourseKind.OUTSIDE:
                continue

            ws_comps = [comp for comp in c.components
                        if comp.component_type == ComponentType.WORKSHOP]
            if not ws_comps:
                continue

            for y in all_years:
                for sem in all_semesters:
                    # Collect all days that have lecture open vars
                    lec_days = sorted({d for (cid, yy, ss, d) in lec_open_by_day
                                       if cid == c.id and yy == y and ss == sem})
                    if not lec_days:
                        continue

                    for ws_comp in ws_comps:
                        for k in inst.allowed_timeslot_keys_for_component(c.id, ws_comp.id):
                            if k.year != y or k.semester != sem:
                                continue
                            ov_ws = vs.open.get((c.id, ws_comp.id, k.id))
                            if ov_ws is None:
                                continue

                            # Collect lecture open vars strictly before this workshop:
                            #   - strictly earlier day: all periods count
                            #   - same day: only periods strictly before the workshop period
                            earlier_lec = []
                            for ld in lec_days:
                                if ld < k.day:
                                    earlier_lec.extend(
                                        ov for _, ov in lec_open_by_day.get((c.id, y, sem, ld), []))
                                elif ld == k.day:
                                    earlier_lec.extend(
                                        ov for p, ov in lec_open_by_day.get((c.id, y, sem, ld), [])
                                        if p < k.period)

                            if earlier_lec:
                                # If workshop is open, at least one earlier lecture must be open
                                model.add(sum(earlier_lec) >= 1).only_enforce_if(ov_ws)
                            else:
                                # No lecture at an earlier slot possible -> forbid this workshop slot
                                model.add(ov_ws == 0)

                            # Same-day: forbid any lecture at period >= workshop period
                            for p_lec, ov_lec in lec_open_by_day.get((c.id, y, sem, k.day), []):
                                if p_lec >= k.period:
                                    model.add(ov_ws + ov_lec <= 1)


    # ----------------------------------------------------------------------------------------------------------
    # Weekly / fortnightly workshop no-overlap: for each non-outside course, weekly workshops
    # and fortnightly workshops cannot be open at the same physical timeslot.
    # (weekly-weekly OK, fortnightly-fortnightly OK, weekly-fortnightly NOT OK)
    # ----------------------------------------------------------------------------------------------------------

    if inst.rules.ws_weekly_fortnightly_no_overlap:
        from data.schema import Frequency

        # Index workshop open vars by (course_id, base_id, frequency)
        ws_by_freq = defaultdict(list)
        for (cid, compid, kid), ov in vs.open.items():
            comp = comp_by_id[(cid, compid)]
            if comp.component_type != ComponentType.WORKSHOP:
                continue
            k = key_by_id[kid]
            ws_by_freq[(cid, k.base_id, comp.frequency)].append((k.week_pattern, ov))

        for c in inst.courses:
            if c.kind == CourseKind.OUTSIDE:
                continue

            bases = {base for (cid, base, _) in ws_by_freq if cid == c.id}
            for base in bases:
                wk_vars = ws_by_freq.get((c.id, base, Frequency.WEEKLY), [])
                fn_vars = ws_by_freq.get((c.id, base, Frequency.FORTNIGHTLY), [])
                if not wk_vars or not fn_vars:
                    continue

                # For each overlapping pattern pair (ALL vs ODD, ALL vs EVEN)
                for wp_wk, wp_fn in [(WeekPattern.ALL, WeekPattern.ODD),
                                     (WeekPattern.ALL, WeekPattern.EVEN)]:
                    ovs_wk = [ov for (wp, ov) in wk_vars if wp == wp_wk]
                    ovs_fn = [ov for (wp, ov) in fn_vars if wp == wp_fn]
                    combined = ovs_wk + ovs_fn
                    if len(combined) > 1:
                        model.add(sum(combined) <= 1)


    # ----------------------------------------------------------------------------------------------------------
    # Max same-type workshops per timeslot: for the same course at any physical
    # timeslot, at most N workshop sections of the same frequency type can be open.
    # ----------------------------------------------------------------------------------------------------------

    max_same_type_ws = inst.rules.max_same_type_ws_per_timeslot
    if max_same_type_ws < 999:
        from data.schema import Frequency

        # Group workshop open vars by (course_id, base_id, week_pattern, frequency)
        ws_global = defaultdict(list)
        for (cid, compid, kid), ov in vs.open.items():
            comp = comp_by_id[(cid, compid)]
            if comp.component_type != ComponentType.WORKSHOP:
                continue
            c = inst.course_by_id[cid]
            if c.kind == CourseKind.OUTSIDE:
                continue
            k = key_by_id[kid]
            ws_global[(cid, k.base_id, k.week_pattern, comp.frequency)].append(ov)

        for (cid, base, wp, freq), ovs in ws_global.items():
            if len(ovs) > max_same_type_ws:
                model.add(sum(ovs) <= max_same_type_ws)


    # ----------------------------------------------------------------------------------------------------------
    # Same-day lectures consecutive: if the same course has >=2 lectures on the same day,
    # they must occupy consecutive time periods (no gap between them).
    # Implementation: for any two non-adjacent periods, forbid both having lectures.
    # ----------------------------------------------------------------------------------------------------------

    if inst.rules.same_day_lectures_consecutive:
        all_days_set = {k.day for k in inst.timeslot_keys_list}
        all_periods_set = sorted({k.period for k in inst.timeslot_keys_list})
        physical_weeks = [
            ("even", {WeekPattern.ALL, WeekPattern.EVEN}),
            ("odd",  {WeekPattern.ALL, WeekPattern.ODD}),
        ]

        for c in inst.courses:
            if c.kind == CourseKind.OUTSIDE:
                continue

            lec_comps = [comp for comp in c.components
                         if comp.component_type == ComponentType.LECTURE]
            if not lec_comps:
                continue

            for y in all_years:
                for sem in all_semesters:
                    for d in all_days_set:
                        for pw_label, wps in physical_weeks:
                            # Collect lecture open vars by period
                            period_ovs = defaultdict(list)
                            for comp in lec_comps:
                                for wp in wps:
                                    for p in all_periods_set:
                                        key_id = f"Y{y}_S{sem}_{wp.value}_D{d}_P{p}"
                                        ov = vs.open.get((c.id, comp.id, key_id))
                                        if ov is not None:
                                            period_ovs[p].append(ov)

                            active_periods = sorted(period_ovs.keys())
                            if len(active_periods) <= 1:
                                continue

                            # Create indicator per period: 1 if any lecture at that period
                            ind_by_p = {}
                            for p in active_periods:
                                ovs = period_ovs[p]
                                if len(ovs) == 1:
                                    ind_by_p[p] = ovs[0]
                                else:
                                    ind = model.new_bool_var(
                                        f"sdlc[{c.id},Y{y},S{sem},{pw_label},D{d},P{p}]")
                                    link_or(model, ovs, ind)
                                    ind_by_p[p] = ind

                            # Forbid any two non-adjacent periods from both having lectures
                            for i in range(len(active_periods)):
                                for j in range(i + 1, len(active_periods)):
                                    p1, p2 = active_periods[i], active_periods[j]
                                    if p2 - p1 > 1:
                                        model.add(ind_by_p[p1] + ind_by_p[p2] <= 1)
