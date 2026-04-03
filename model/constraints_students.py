from collections import defaultdict
from ortools.sat.python import cp_model

from data.schema import CourseKind, ProgrammeKind, WeekPattern, Instance
from model.variables import VarSets
from model.utils import is_sectioned


def add_student_constraints(model: cp_model.CpModel, inst: Instance, vs: VarSets):

    # Pre-compute useful idxes and lookups
    course_by_id = inst.course_by_id
    key_by_id    = inst.timeslot_key_by_id

    gateway_ids  = set(inst.gateway_course_ids)
    optional_ids = set(inst.optional_course_ids)

    all_years     = inst.all_years
    all_semesters = inst.all_semesters

    # Take vars indexed by (student_type, year, semester) -> {course_id: var}
    take_by_sys = defaultdict(dict)
    for (sid, cid, y, sem), tv in vs.take.items():
        take_by_sys[(sid, y, sem)][cid] = tv

    # Per-student (year, semester) keys for efficient lookup (used by symmetry breaking)
    take_ys_by_student = defaultdict(list)
    for (sid, y, sem) in take_by_sys:
        take_ys_by_student[sid].append((y, sem))

    # Student counts for weighting enrollment sums
    count_of = {s.id: s.number_students for s in inst.students}

    # Take vars indexed by (course, year, semester) -> [weighted expr]
    # Each entry is N_i * take_bool so sum gives total student enrollment.
    take_by_cys = defaultdict(list)
    for (sid, cid, y, sem), tv in vs.take.items():
        take_by_cys[(cid, y, sem)].append(count_of[sid] * tv)

    # Assign vars indexed by (student_type, course, component, year, semester) -> [var]
    assign_by_sct = defaultdict(list)
    for (sid, cid, compid, kid), av in vs.assign.items():
        kk = key_by_id[kid]
        assign_by_sct[(sid, cid, compid, kk.year, kk.semester)].append(av)

    # Sectioned components indexed by course_id -> [(component_id, component_obj)]
    sectioned_by_course = defaultdict(list)
    for c in inst.courses:
        for comp in c.components:
            if is_sectioned(comp):
                sectioned_by_course[c.id].append((comp.id, comp))


    # ----------------------------------------------------------------------------------------------------------
    # Per-student-type constraints
    # All students within the same aggregated type share an identical schedule.
    # take/assign are BoolVar — no scaling by N needed for per-type rules.
    # ----------------------------------------------------------------------------------------------------------

    for s in inst.students:
        rule    = inst.rules.for_student(s)
        s_years = inst.years_for_student(s)
        s_sems  = inst.semesters_for_student(s)

        all_gw_vars    = []                    # across all years / sems
        course_takes   = defaultdict(list)     # cid -> [var]

        # Collect per-semester credit sums for balanced_credits
        sem_credit_sums = {}                   # (y, sem) -> linear expr

        for y in s_years:
            year_total   = []    # weighted credit terms
            year_outside = []    # weighted outside-credit terms
            year_gw      = []    # gateway vars this year
            year_opt     = []    # optional vars this year
            year_all     = []    # all non-banned vars

            for sem in s_sems:
                sem_gw  = []     # gateway vars this semester
                sem_opt = []     # optional vars this semester
                sem_all = []     # all non-banned vars
                sem_credits = [] # weighted credit terms

                for cid, tv in take_by_sys.get((s.id, y, sem), {}).items():
                    c = course_by_id[cid]

                    # Accumulate for aggregation constraints
                    course_takes[cid].append(tv)
                    year_total.append(tv * c.credits)
                    sem_credits.append(tv * c.credits)
                    sem_all.append(tv)
                    year_all.append(tv)

                    if s.programme != ProgrammeKind.SINGLE and c.kind == CourseKind.OUTSIDE:
                        year_outside.append(tv * c.credits)

                    if cid in gateway_ids:
                        sem_gw.append(tv)
                        year_gw.append(tv)
                        all_gw_vars.append(tv)
                    elif cid in optional_ids:
                        sem_opt.append(tv)
                        year_opt.append(tv)

                # Per-semester gateway bounds
                if sem_gw:
                    if rule.gateway_min_per_semester > 0:
                        model.add(sum(sem_gw) >= rule.gateway_min_per_semester)
                    if rule.gateway_max_per_semester < 999:
                        model.add(sum(sem_gw) <= rule.gateway_max_per_semester)

                # Per-semester optional bounds
                if sem_opt:
                    if rule.optional_min_per_semester > 0:
                        model.add(sum(sem_opt) >= rule.optional_min_per_semester)
                    if rule.optional_max_per_semester < 999:
                        model.add(sum(sem_opt) <= rule.optional_max_per_semester)

                # Per-semester total course count bounds
                if sem_all:
                    if rule.courses_min_per_semester > 0:
                        model.add(sum(sem_all) >= rule.courses_min_per_semester)
                    if rule.courses_max_per_semester < 999:
                        model.add(sum(sem_all) <= rule.courses_max_per_semester)

                # Per-semester credit bounds
                if sem_credits:
                    sem_credit_expr = sum(sem_credits)
                    sem_credit_sums[(y, sem)] = sem_credit_expr
                    if rule.credits_min_per_semester > 0:
                        model.add(sem_credit_expr >= rule.credits_min_per_semester)
                    if rule.credits_max_per_semester < 999:
                        model.add(sem_credit_expr <= rule.credits_max_per_semester)

            # Credit requirements for this year
            if year_total:
                model.add(sum(year_total) == rule.total_credits_per_year)
            if rule.outside_credits_required_per_year > 0 and year_outside:
                model.add(sum(year_outside) >= rule.outside_credits_required_per_year)

            # Per-year gateway bounds
            if year_gw:
                if rule.gateway_min_per_year > 0:
                    model.add(sum(year_gw) >= rule.gateway_min_per_year)
                if rule.gateway_max_per_year < 999:
                    model.add(sum(year_gw) <= rule.gateway_max_per_year)

            # Per-year optional bounds
            if year_opt:
                opt_sum = sum(year_opt)

                if rule.optional_max_per_year < 999:
                    model.add(opt_sum <= rule.optional_max_per_year)

                # Conditional: if type takes optional -> enforce min
                if rule.optional_min_per_year > 0:
                    has_opt = model.new_bool_var(f"has_opt[{s.id},Y{y}]")
                    model.add(opt_sum >= 1).OnlyEnforceIf(has_opt)
                    model.add(opt_sum == 0).OnlyEnforceIf(has_opt.Not())
                    model.add(opt_sum >= rule.optional_min_per_year).OnlyEnforceIf(has_opt)

            # Per-year total course count bounds
            if year_all:
                if rule.courses_min_per_year > 0:
                    model.add(sum(year_all) >= rule.courses_min_per_year)
                if rule.courses_max_per_year < 999:
                    model.add(sum(year_all) <= rule.courses_max_per_year)

        # Balanced credits across semesters within each year
        if rule.balanced_credits and len(s_sems) == 2:
            for y in s_years:
                s1_expr = sem_credit_sums.get((y, s_sems[0]))
                s2_expr = sem_credit_sums.get((y, s_sems[1]))
                if s1_expr is not None and s2_expr is not None:
                    model.add(s1_expr == s2_expr)

        # Total gateway requirement across all years
        if all_gw_vars:
            model.add(sum(all_gw_vars) >= rule.gateway_total_required)

        # Compulsory courses — type must take each
        for cid in s.compulsory_course_ids:
            takes = [take_by_sys.get((s.id, y, sem), {}).get(cid)
                     for y in s_years for sem in s_sems]
            takes = [tv for tv in takes if tv is not None]
            if takes:
                model.add(sum(takes) >= 1)

        # Each course taken at most once
        for cid, tvs in course_takes.items():
            if len(tvs) > 1:
                model.add(sum(tvs) <= 1)

        # Component attendance for sectioned components
        # sum(assigns) == number_per_week * take_int
        # (take_int already represents how many students take the course)
        for y in s_years:
            for sem in s_sems:
                for cid in take_by_sys.get((s.id, y, sem), {}):
                    for compid, comp in sectioned_by_course.get(cid, []):
                        take_var = vs.take[(s.id, cid, y, sem)]
                        assigns = assign_by_sct.get((s.id, cid, compid, y, sem), [])
                        if assigns:
                            model.add(sum(assigns) == comp.number_per_week * take_var)
                        else:
                            model.add(take_var == 0)


    # ----------------------------------------------------------------------------------------------------------
    # Symmetry breaking for subgroups from the same parent type.
    # If type s_i and s_{i+1} share the same parent_type, enforce
    #   take[s_i, c, y, sem] >= take[s_{i+1}, c, y, sem]
    # so that earlier subgroups always take a superset of courses.
    # ----------------------------------------------------------------------------------------------------------

    # Group subgroups by parent_type (dict preserves insertion order in Python 3.7+)
    sibling_groups: dict[str, list] = {}
    for s in inst.students:
        if s.parent_type is not None:
            sibling_groups.setdefault(s.parent_type, []).append(s.id)

    for _, sib_ids in sibling_groups.items():
        if len(sib_ids) < 2:
            continue
        for i in range(len(sib_ids) - 1):
            s_hi = sib_ids[i]
            s_lo = sib_ids[i + 1]
            for (y, sem) in take_ys_by_student.get(s_hi, []):
                cid_map = take_by_sys[(s_hi, y, sem)]
                cid_map_lo = take_by_sys.get((s_lo, y, sem), {})
                for cid, tv_hi in cid_map.items():
                    tv_lo = cid_map_lo.get(cid)
                    if tv_lo is not None:
                        model.add(tv_hi >= tv_lo)


    # ----------------------------------------------------------------------------------------------------------
    # take -> active linkage (BoolVar implication)
    # ----------------------------------------------------------------------------------------------------------

    for (sid, cid, y, sem), take_var in vs.take.items():
        act = vs.active.get((cid, y, sem))
        if act is None:
            # No active var for this (course, year, semester) — force take=0
            model.add(take_var == 0)
        else:
            model.add_implication(take_var, act)

    # ----------------------------------------------------------------------------------------------------------
    # Course-level enrolment caps
    # ----------------------------------------------------------------------------------------------------------

    for c in inst.courses:
        if c.cap_max >= 999 and c.cap_min <= 0:
            continue                          # no binding cap -> skip
        for y in all_years:
            for sem in all_semesters:
                enrollments = take_by_cys.get((c.id, y, sem), [])
                if not enrollments:
                    continue
                act_key = (c.id, y, sem)
                if act_key not in vs.active:
                    continue
                act = vs.active[act_key]
                s = sum(enrollments)
                if c.cap_max < 999:
                    model.add(s <= c.cap_max).OnlyEnforceIf(act)
                if c.cap_min > 0:
                    model.add(s >= c.cap_min).OnlyEnforceIf(act)


    # ----------------------------------------------------------------------------------------------------------
    # Student max daily gap AND student max slots per day.
    # Both constraints share the same per-period attendance indicator variables.
    #
    # Daily gap: for any pair (p_i, p_j) with distance p_j − p_i > max_gap,
    #   att[p_i] + att[p_j]  ≤  1 + Σ att[p_m]   (for all p_m with p_i < p_m < p_j)
    #
    # Max slots per day: sum of attend variables per day ≤ max_slots.
    # ----------------------------------------------------------------------------------------------------------

    max_gap = inst.rules.student_max_daily_gap
    max_slots = inst.rules.student_max_slots_per_day
    max_consec = inst.rules.student_max_consecutive_slots
    need_attend = (max_gap < 999) or (max_slots < 999) or (max_consec < 999)

    if need_attend:

        all_days_set = {k.day for k in inst.timeslot_keys_list}
        all_periods_set = {k.period for k in inst.timeslot_keys_list}
        physical_weeks = [
            ("even", {WeekPattern.ALL, WeekPattern.EVEN}),
            ("odd",  {WeekPattern.ALL, WeekPattern.ODD}),
        ]

        # Pre-index open vars by (cid, compid, y, sem, wp, d, p)
        open_detail = {}
        for (cid, compid, kid), ov in vs.open.items():
            k = key_by_id[kid]
            open_detail[(cid, compid, k.year, k.semester,
                         k.week_pattern, k.day, k.period)] = ov

        # Pre-index assign vars by (sid, cid, compid, y, sem, wp, d, p)
        assign_detail = {}
        for (sid, cid, compid, kid), av in vs.assign.items():
            k = key_by_id[kid]
            assign_detail[(sid, cid, compid, k.year, k.semester,
                           k.week_pattern, k.day, k.period)] = av

        for s in inst.students:
            s_years = inst.years_for_student(s)
            s_sems = inst.semesters_for_student(s)

            for y in s_years:
                for sem in s_sems:
                    courses_in_sem = take_by_sys.get((s.id, y, sem), {})
                    if not courses_in_sem:
                        continue

                    for d in all_days_set:
                        for pw_label, wps in physical_weeks:
                            # attend: all courses (used for max_slots and max_consec)
                            attend = {}
                            # attend_noout: only non-outside courses (used for max_gap,
                            # because outside courses have fixed timeslots we cannot move)
                            attend_noout = {}

                            for p in all_periods_set:
                                links = []
                                links_noout = []

                                for cid, take_var in courses_in_sem.items():
                                    c_obj = course_by_id[cid]
                                    is_outside = (c_obj.kind == CourseKind.OUTSIDE)
                                    for comp in c_obj.components:
                                        for wp in wps:
                                            if not is_sectioned(comp):
                                                ov = open_detail.get(
                                                    (cid, comp.id, y, sem, wp, d, p))
                                                if ov is not None:
                                                    links.append(('lec', take_var, ov))
                                                    if not is_outside:
                                                        links_noout.append(('lec', take_var, ov))
                                            else:
                                                av = assign_detail.get(
                                                    (s.id, cid, comp.id, y, sem, wp, d, p))
                                                if av is not None:
                                                    links.append(('ws', av))
                                                    if not is_outside:
                                                        links_noout.append(('ws', av))

                                if not links:
                                    continue

                                att = model.new_bool_var(
                                    f"att[{s.id},Y{y},S{sem},{pw_label},D{d},P{p}]")

                                active_indicators = []

                                for lk in links:
                                    if lk[0] == 'lec':
                                        _, tv, ov = lk
                                        # lecture attendance indicator for (take AND open)
                                        lec_on = model.new_bool_var(
                                            f"att_lec_on[{s.id},Y{y},S{sem},{pw_label},D{d},P{p},i{len(active_indicators)}]")
                                        model.add(lec_on <= tv)
                                        model.add(lec_on <= ov)
                                        model.add(lec_on >= tv + ov - 1)
                                        active_indicators.append(lec_on)
                                        model.add(att >= lec_on)
                                    else:  # workshop
                                        _, av = lk
                                        # att fires when assign = 1
                                        active_indicators.append(av)
                                        model.add(att >= av)

                                # Prevent artificial attend=1 when no class is active at this period.
                                model.add(att <= sum(active_indicators))

                                attend[p] = att

                                # Build attend_noout (non-outside courses only, for gap constraint)
                                if links_noout:
                                    att_no = model.new_bool_var(
                                        f"att_no[{s.id},Y{y},S{sem},{pw_label},D{d},P{p}]")
                                    no_indicators = []
                                    for lk in links_noout:
                                        if lk[0] == 'lec':
                                            _, tv, ov = lk
                                            lec_on_no = model.new_bool_var(
                                                f"att_lno[{s.id},Y{y},S{sem},{pw_label},D{d},P{p},i{len(no_indicators)}]")
                                            model.add(lec_on_no <= tv)
                                            model.add(lec_on_no <= ov)
                                            model.add(lec_on_no >= tv + ov - 1)
                                            no_indicators.append(lec_on_no)
                                            model.add(att_no >= lec_on_no)
                                        else:
                                            _, av = lk
                                            no_indicators.append(av)
                                            model.add(att_no >= av)
                                    model.add(att_no <= sum(no_indicators))
                                    attend_noout[p] = att_no

                            # Consecutive-gap elimination (only for non-outside courses)
                            if max_gap < 999:
                                periods = sorted(attend_noout.keys())
                                for i in range(len(periods)):
                                    for j in range(i + 1, len(periods)):
                                        if periods[j] - periods[i] > max_gap:
                                            between = [attend_noout[periods[m]]
                                                       for m in range(i + 1, j)]
                                            if between:
                                                model.add(
                                                    attend_noout[periods[i]] +
                                                    attend_noout[periods[j]]
                                                    <= 1 + sum(between))
                                            else:
                                                model.add(
                                                    attend_noout[periods[i]] +
                                                    attend_noout[periods[j]] <= 1)

                            # Max slots per day (all courses)
                            if max_slots < 999 and attend:
                                model.add(sum(attend.values()) <= max_slots)

                            # Max consecutive slots: no window of (K+1)
                            # consecutively-numbered periods can all be attended.
                            if max_consec < 999 and len(attend) > max_consec:
                                periods = sorted(attend.keys())
                                window = max_consec + 1
                                for i in range(len(periods) - window + 1):
                                    # Only constrain truly consecutive period indices
                                    run = periods[i:i + window]
                                    if run[-1] - run[0] == window - 1:
                                        model.add(
                                            sum(attend[p] for p in run) <= max_consec)
