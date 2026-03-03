from collections import defaultdict
from ortools.sat.python import cp_model

from data.schema import CourseKind, WeekPattern, Instance
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
        gw = [sem_ind_map[(c.id, sem)] for c in inst.courses if c.kind == CourseKind.GATEWAY and (c.id, sem) in sem_ind_map]
        opt = [sem_ind_map[(c.id, sem)] for c in inst.courses if c.kind == CourseKind.OPTIONAL and (c.id, sem) in sem_ind_map]
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
    # For a given course, there cannot be internal timetable conflicts between its components.
    # (which can restrict by consider even/odd week patterns for different components in the same base slot)
    # ----------------------------------------------------------------------------------------------------------

    for c in inst.courses:
        bases = {base for (cid, base, _) in open_by_base_wp if cid == c.id}
        for base in bases:
            s_all = sum_vars(open_by_base_wp.get((c.id, base, WeekPattern.ALL), []))
            s_odd = sum_vars(open_by_base_wp.get((c.id, base, WeekPattern.ODD), []))
            s_evn = sum_vars(open_by_base_wp.get((c.id, base, WeekPattern.EVEN), []))
            model.add(s_all <= 1)
            model.add(s_odd <= 1)
            model.add(s_evn <= 1)
            model.add(s_all + s_odd <= 1)
            model.add(s_all + s_evn <= 1)


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
