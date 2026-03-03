"""
Output files
────────────────────────────────────────────────────────────────────────
1. timetable.csv              Open timeslots for every course component
2. student_courses.csv        Which courses each student takes
3. enrollment.csv             Course enrollment with programme breakdown
4. student_assignments.csv    Student → section/timeslot mapping
5. conflicts.csv              Pairwise student timetable clashes
6. conflict_summary.csv       Per-programme & overall conflict statistics
7. solution_summary.csv       High-level solver result (objective, counts …)
"""

from collections import defaultdict
from pathlib import Path

from data.schema import ComponentType
from model.utils import is_sectioned, patterns_overlap
from data.utils import write_csv
from utils import weighted_median


DAY_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

# ──────────────────────────────────────────────────────────────────────
# Main output
# ──────────────────────────────────────────────────────────────────────

def write_all_outputs(inst, vs, solver, out):
    """Extract solution values and write every output CSV."""
    out = Path(out)

    # Shared look-ups built once
    key_by_id = inst.timeslot_key_by_id
    comp_by_id = {(c.id, comp.id): comp for c in inst.courses for comp in c.components}
    course_by_id = inst.course_by_id
    prog_of = {s.id: s.programme for s in inst.students}
    count_of = {s.id: s.number_students for s in inst.students}

    write_timetable(inst, vs, solver, out, key_by_id, comp_by_id, course_by_id)
    write_student_courses(vs, solver, out, course_by_id, prog_of, count_of)
    write_enrollment(inst, vs, solver, out, course_by_id, prog_of, count_of)
    write_student_assignments(inst, vs, solver, out, key_by_id, comp_by_id, course_by_id, prog_of, count_of)
    conflict_rows = write_conflicts(inst, vs, solver, out, key_by_id, comp_by_id, prog_of, count_of)
    write_conflict_summary(inst, conflict_rows, out)
    write_solution_summary(inst, vs, solver, conflict_rows, out)


# ──────────────────────────────────────────────────────────────────────
# timetable.csv
# ──────────────────────────────────────────────────────────────────────

def write_timetable(inst, vs, solver, out, key_by_id, comp_by_id, course_by_id):
    rows = []
    for (cid, compid, kid), ov in vs.open.items():
        # Skip if this component isn't open in the solution.
        if solver.Value(ov) != 1:
            continue

        k = key_by_id[kid]
        comp = comp_by_id[(cid, compid)]
        c = course_by_id[cid]

        rows.append([
            cid, c.name, c.kind.value,
            compid, comp.component_type.value,
            k.year, k.semester,
            DAY_NAMES.get(k.day, k.day),
            k.period,
            inst.format_period_time(k.period),
            k.week_pattern.value,
            kid,
        ])

    rows.sort(key=lambda r: (r[5], r[6], r[0], r[3]))
    write_csv(out / "timetable.csv",
              ["course_id", "course_name", "course_kind", "component_id", "component_type",
               "year", "semester", "day", "period", "time", "week_pattern", "timeslot_key_id"], rows)


# ──────────────────────────────────────────────────────────────────────
# student_courses.csv
# ──────────────────────────────────────────────────────────────────────

def write_student_courses(vs, solver, out, course_by_id, prog_of, count_of):
    bucket = defaultdict(list)
    for (sid, cid, y, sem), tv in vs.take.items():
        # Skip if student type doesn't take this course/year/semester
        if solver.Value(tv) == 0:
            continue
        
        # All students in the type share the same schedule, so weight by number_students for proper scaling in summary stats.
        c = course_by_id[cid]
        bucket[(sid, y)].append((cid, c.name, c.kind.value, c.credits, sem, count_of[sid]))

    rows = []
    for (sid, y), courses in sorted(bucket.items()):
        for cid, cname, ckind, credits, sem, n_take in sorted(courses, key=lambda x: (x[4], x[0])):
            rows.append([sid, prog_of[sid].value, count_of[sid], n_take, y, sem, cid, cname, ckind, credits])

    write_csv(out / "student_courses.csv",
              ["student_type_id", "programme", "number_students", "students_taking",
               "year", "semester", "course_id", "course_name", "course_kind", "credits"], rows)


# ──────────────────────────────────────────────────────────────────────
# enrollment.csv
# ──────────────────────────────────────────────────────────────────────

def write_enrollment(inst, vs, solver, out, course_by_id, prog_of, count_of):
    # Gather active course/year/semester combinations from active vars
    active_set = set()
    for (cid, y, sem), av in vs.active.items():
        if solver.Value(av) == 1:
            active_set.add((cid, y, sem))

    # enrollment by (course, year, semester, programme) — weighted
    enrol = defaultdict(int)           # (cid, y, sem, prog) -> total students
    enrol_total = defaultdict(int)     # (cid, y, sem) -> total students

    # Also collect programmes per (cid, y, sem)
    progs_by_cys = defaultdict(set)
    for (sid, cid, y, sem), tv in vs.take.items():
        # Skip if student type doesn't take this course/year/semester
        if solver.Value(tv) == 0:
            continue

        n = count_of[sid]
        prog = prog_of[sid].value
        enrol[(cid, y, sem, prog)] += n
        enrol_total[(cid, y, sem)] += n
        progs_by_cys[(cid, y, sem)].add(prog)

    rows = []
    for c in inst.courses:
        active_entries = sorted(k for k in active_set if k[0] == c.id)

        # skip courses with no active entries (not offered in any year/semester) — write single row with "NA" for year/semester, and 0 enrollment
        if not active_entries:
            rows.append([c.id, c.name, c.kind.value, c.credits, "NA", "NA", "ALL", 0])
            continue

        for cid, y, sem in active_entries:
            total = enrol_total.get((cid, y, sem), 0)
            rows.append([cid, c.name, c.kind.value, c.credits, y, sem, "ALL", total])
            
            # Programme Summary: break down enrollment by programme for this course/year/semester
            progs = sorted(progs_by_cys.get((cid, y, sem), set()))
            
            for prog in progs:
                n = enrol.get((cid, y, sem, prog), 0)
                rows.append([cid, c.name, c.kind.value, c.credits, y, sem, prog, n])

    write_csv(out / "enrollment.csv",
              ["course_id", "course_name", "course_kind", "credits", "year", "semester", "programme", "students_enrolled"], rows)


# ──────────────────────────────────────────────────────────────────────
# student_assignments.csv
# ──────────────────────────────────────────────────────────────────────

def write_student_assignments(inst, vs, solver, out, key_by_id, comp_by_id, course_by_id, prog_of, count_of):
    # Each row: student_type + course + component -> specific section / timeslot.
    rows = []

    # open sections per component per (year,semester)
    open_sections = defaultdict(list)
    for (cid, compid, kid), ov in vs.open.items():
        # Skip if this component isn't open in the solution.
        if solver.Value(ov) != 1:
            continue

        k = key_by_id[kid]
        open_sections[(cid, compid, k.year, k.semester)].append(kid)

    for v in open_sections.values():
        v.sort()

    # Sectioned components — assign is BoolVar (all students in type share the schedule)
    for (sid, cid, compid, kid), av in vs.assign.items():
        # Skip if student type isn't assigned to this section (component/year/semester)
        if solver.Value(av) == 0:
            continue

        n_assigned = count_of[sid]
        k = key_by_id[kid]
        comp = comp_by_id[(cid, compid)]
        c = course_by_id[cid]

        sec_list = open_sections.get((cid, compid, k.year, k.semester), [])
        total_sections = len(sec_list)
        section_index  = (sec_list.index(kid) + 1) if kid in sec_list else 0

        rows.append([
            sid, prog_of[sid].value, count_of[sid], n_assigned,
            k.year, k.semester,
            cid, c.name, compid, comp.component_type.value,
            total_sections, section_index,
            DAY_NAMES.get(k.day, k.day),
            inst.format_period_time(k.period),
            k.week_pattern.value, kid,
        ])

    # Non-sectioned components (lectures / single-section workshops)
    for (cid, compid, kid), ov in vs.open.items():
        # Skip if this component isn't open in the solution.
        if solver.Value(ov) != 1:
            continue
        
        # skip sectioned components since attendance is determined by assign vars, not open vars
        comp = comp_by_id[(cid, compid)]
        if is_sectioned(comp):
            continue

        k = key_by_id[kid]
        c = course_by_id[cid]
        for s in inst.students:
            tk = (s.id, cid, k.year, k.semester)
            tv = vs.take.get(tk)

            # Skip if student type doesn't take this course/year/semester
            if tv is None or solver.Value(tv) == 0:
                continue

            n_take = count_of[s.id]
            rows.append([
                s.id, prog_of[s.id].value, count_of[s.id], n_take,
                k.year, k.semester,
                cid, c.name, compid, comp.component_type.value,
                1, 1,
                DAY_NAMES.get(k.day, k.day),
                inst.format_period_time(k.period),
                k.week_pattern.value, kid,
            ])

    rows.sort(key=lambda r: (r[0], r[4], r[5], r[6], r[8]))
    write_csv(out / "student_assignments.csv",
              ["student_type_id", "programme", "number_students", "assigned_students",
               "year", "semester", "course_id", "course_name", "component_id", "component_type",
               "total_sections", "section_index", "day", "time", "week_pattern", "timeslot_key_id"], rows)


# ──────────────────────────────────────────────────────────────────────
# conflicts.csv
# ──────────────────────────────────────────────────────────────────────

def write_conflicts(inst, vs, solver, out, key_by_id, comp_by_id, prog_of, count_of):
    student_attend = defaultdict(list)

    for (sid, cid, compid, kid), av in vs.assign.items():
        # Skip if student type isn't assigned to this section (component/year/semester)
        if solver.Value(av) == 0:
            continue

        k = key_by_id[kid]
        comp = comp_by_id[(cid, compid)]
        base = k.base_id
        student_attend[(sid, base)].append((cid, compid, k.week_pattern, comp.component_type, k))

    for (cid, compid, kid), ov in vs.open.items():
        # Skip if this component isn't open in the solution.
        if solver.Value(ov) != 1:
            continue

        # skip sectioned components since attendance is determined by assign vars, not open vars
        comp = comp_by_id[(cid, compid)]
        if is_sectioned(comp):
            continue

        k = key_by_id[kid]
        base = k.base_id
        for s in inst.students:
            tk = (s.id, cid, k.year, k.semester)
            tv = vs.take.get(tk)

            if tv is not None and solver.Value(tv) > 0:
                student_attend[(s.id, base)].append((cid, compid, k.week_pattern, comp.component_type, k))

    conflict_rows = []
    for (sid, _), entries in student_attend.items():
        if len(entries) <= 1:
            continue

        n_stu = count_of[sid]

        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                cid1, comp1, wp1, ct1, k1 = entries[i]
                cid2, comp2, wp2, ct2, k2 = entries[j]

                if not patterns_overlap(wp1, wp2):
                    continue

                both_lec = (ct1 == ComponentType.LECTURE and ct2 == ComponentType.LECTURE)
                any_lec  = (ct1 == ComponentType.LECTURE or  ct2 == ComponentType.LECTURE)
                severity = ("lecture_lecture" if both_lec else "lecture_workshop" if any_lec else "workshop_workshop")

                conflict_rows.append([
                    sid, prog_of[sid].value, n_stu,
                    k1.year, k1.semester,
                    DAY_NAMES.get(k1.day, k1.day),
                    inst.format_period_start(k1.period),
                    cid1, comp1, ct1.value,
                    cid2, comp2, ct2.value,
                    severity,
                ])

    conflict_rows.sort()
    write_csv(out / "conflicts.csv",
              ["student_type_id", "programme", "number_students",
               "year", "semester", "day", "time",
               "course_1", "component_1", "type_1", "course_2", "component_2", "type_2", "severity"], conflict_rows)
    
    return conflict_rows


# ──────────────────────────────────────────────────────────────────────
# conflict_summary.csv
# ──────────────────────────────────────────────────────────────────────

def write_conflict_summary(inst, conflict_rows, out):
    programmes = sorted({s.programme.value for s in inst.students})

    # conflict_rows layout: [sid, prog, n_stu, year, sem, day, time, c1, comp1, t1, c2, comp2, t2, severity]
    # count_of = {s.id: s.number_students for s in inst.students}

    conflicts_per_type = defaultdict(int)            # sid -> pairwise conflict count
    severity_per_type = defaultdict(lambda: defaultdict(int))
    for r in conflict_rows:
        sid, sev = r[0], r[-1]
        conflicts_per_type[sid] += 1
        severity_per_type[sid][sev] += 1

    rows = []
    for prog in programmes:
        prog_students = [s for s in inst.students if s.programme.value == prog]
        n_stu = sum(s.number_students for s in prog_students)
        if n_stu == 0:
            continue

        # Weighted conflict counts: each pairwise conflict × number_students
        weighted_counts = [conflicts_per_type.get(s.id, 0) * s.number_students for s in prog_students]
        total = sum(weighted_counts)

        # Per-student average (total conflicts / total students)
        avg = total / n_stu if n_stu else 0

        # Compute weighted severity totals
        sev_totals = defaultdict(int)
        for s in prog_students:
            for sev, cnt in severity_per_type.get(s.id, {}).items():
                sev_totals[sev] += cnt * s.number_students

        # Types (not individual students) with conflicts, weighted
        with_conflict = sum(s.number_students for s in prog_students if conflicts_per_type.get(s.id, 0) > 0)

        # Median: weighted (efficient, no expansion)
        med = weighted_median(
            [(conflicts_per_type.get(s.id, 0), s.number_students) for s in prog_students])

        rows.append([
            prog, n_stu, total,
            sev_totals.get("lecture_lecture", 0),
            sev_totals.get("lecture_workshop", 0),
            sev_totals.get("workshop_workshop", 0),
            f"{avg:.2f}", f"{med:.1f}",
            with_conflict,
            f"{100 * with_conflict / n_stu:.1f}%",
        ])

    # Overall row
    total_students = sum(s.number_students for s in inst.students)
    all_weighted = [conflicts_per_type.get(s.id, 0) * s.number_students for s in inst.students]
    all_total = sum(all_weighted)
    all_with = sum(s.number_students for s in inst.students if conflicts_per_type.get(s.id, 0) > 0)
    all_avg = all_total / total_students if total_students else 0
    all_med = weighted_median([(conflicts_per_type.get(s.id, 0), s.number_students) for s in inst.students])

    all_sev = defaultdict(int)
    for r in conflict_rows:
        all_sev[r[-1]] += r[2]  # r[2] = number_students

    rows.append([
        "ALL", total_students, all_total,
        all_sev.get("lecture_lecture", 0),
        all_sev.get("lecture_workshop", 0),
        all_sev.get("workshop_workshop", 0),
        f"{all_avg:.2f}", f"{all_med:.1f}",
        all_with,
        f"{100 * all_with / max(1, total_students):.1f}%",
    ])

    write_csv(out / "conflict_summary.csv",
              ["programme", "students", "total_conflicts",
               "lecture_lecture", "lecture_workshop", "workshop_workshop",
               "mean_per_student", "median_per_student",
               "students_with_conflicts", "pct_with_conflicts"],
              rows)


# ──────────────────────────────────────────────────────────────────────
# 7. solution_summary.csv  (replaces console prints)
# ──────────────────────────────────────────────────────────────────────

def write_solution_summary(inst, vs, solver, conflict_rows, out):
    total_students = sum(s.number_students for s in inst.students)
    n_types = len(inst.students)

    # Weighted conflict counting
    cps = defaultdict(int)
    for r in conflict_rows:
        cps[r[0]] += 1

    # conflict_rows have number_students at index 2
    n_conflicts_weighted = sum(cps[s.id] * s.number_students for s in inst.students)

    ll = sum(r[2] for r in conflict_rows if r[-1] == "lecture_lecture")
    lw = sum(r[2] for r in conflict_rows if r[-1] == "lecture_workshop")
    ww = sum(r[2] for r in conflict_rows if r[-1] == "workshop_workshop")

    students_with = sum(s.number_students for s in inst.students if cps.get(s.id, 0) > 0)
    count_of = {s.id: s.number_students for s in inst.students}
    total_take = sum(count_of[sid] for (sid, cid, y, sem), tv in vs.take.items() if solver.Value(tv) > 0)
    active_courses = sum(1 for av in vs.active.values() if solver.Value(av) == 1)
    avg = n_conflicts_weighted / total_students if total_students else 0
    med = weighted_median([(cps.get(s.id, 0), s.number_students) for s in inst.students])

    write_csv(out / "solution_summary.csv",
              ["metric", "value"],
              [
                  ["objective_value", solver.ObjectiveValue()],
                  ["best_bound", solver.BestObjectiveBound()],
                  ["total_students", total_students],
                  ["student_types", n_types],
                  ["total_take_vars_weighted", total_take],
                  ["active_courses", active_courses],
                  ["conflicts_total", n_conflicts_weighted],
                  ["conflicts_lec_lec", ll],
                  ["conflicts_lec_ws", lw],
                  ["conflicts_ws_ws", ww],
                  ["students_with_conflict", students_with],
                  ["pct_with_conflict", f"{100 * students_with / max(1, total_students):.1f}%"],
                  ["mean_conflicts_per_stu", f"{avg:.2f}"],
                  ["median_conflicts_per_stu", f"{med:.1f}"],
              ])