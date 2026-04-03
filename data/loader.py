import math
from collections import defaultdict
from itertools import product
from pathlib import Path

from data.utils import *
from data.schema import *

# ── Main ────────────────────────────────────────────────────────────────────
def load_instance(instance_dir, validate = True):
    dir = Path(instance_dir)

    if not dir.exists() or not dir.is_dir():
        raise FileNotFoundError(f"instance_dir not found in path: {dir}")

    keys, start_min, slot_min = generate_timeslot_keys(dir / "timeslot_config.json")
    rules = load_rules(dir / "rules.json")

    inst = Instance(
        rules = rules,
        timeslot_keys_list = keys,
        courses = load_courses_and_components(dir / "courses.csv", dir / "components.csv"),
        students = load_students(dir / "students.csv", rules.max_group_size),
        slot_start_minutes = start_min,
        slot_duration_minutes = slot_min,
    )

    if validate:
        inst.validate()

    return inst


# ── Timeslot Keys ────────────────────────────────────────────────────────────
def generate_timeslot_keys(path):
    cfg = read_json(path)

    years = cfg.get("years", None)
    semesters = cfg.get("semesters", None)

    active_days = cfg.get("days", {}).get("active_days", [0, 1, 2, 3, 4])

    time_cfg = cfg.get("time", {})
    start_min = to_minutes(str(time_cfg.get("start", "09:00")))
    end_min = to_minutes(str(time_cfg.get("end", "18:00")))
    slot_minutes = int(time_cfg.get("slot_minutes", 60))

    span = end_min - start_min
    if span % slot_minutes != 0:
        raise ValueError("timeslot_config.json: (end - start) must be divisible by slot_minutes.")
    period_range = range(span // slot_minutes)

    wp_raw = cfg.get("week_patterns", ["every_week", "odd_weeks", "even_weeks"])
    week_patterns = [parse_enum(WeekPattern, s, field_name="week_patterns item") for s in wp_raw]

    keys = [
        TimeslotKey(year=int(y), semester=int(s), week_pattern=wp, day=int(d), period=int(p))
        for y, s, wp, d, p in product(years, semesters, week_patterns, active_days, period_range)
    ]
    return keys, start_min, slot_minutes


# ── Rules ────────────────────────────────────────────────────────────────────
def load_rules(path):
    raw  =  read_json(path)
    by_type  =  {}

    # Extract global timetable parameters (backwards-compatible defaults)
    max_grp  = int(raw.pop("max_group_size", 999))
    global_gw  = int(raw.pop("global_gateway_per_semester", 4))
    global_opt = int(raw.pop("global_optional_per_semester", 2))
    student_gap = int(raw.pop("student_max_daily_gap", 999))
    student_slots = int(raw.pop("student_max_slots_per_day", 999))
    course_day  = int(raw.pop("course_max_slots_per_day", 999))
    lec_per_day  = int(raw.pop("lecture_max_per_day", 999))
    ws_per_day = int(raw.pop("workshop_max_per_day", 999))
    ws_after_lec = bool(raw.pop("workshop_after_lecture", False))
    max_conc_courses = int(raw.pop("max_concurrent_courses_per_timeslot", 999))
    lunch_no_class = bool(raw.pop("lunch_break_no_class", False))
    max_consec = int(raw.pop("student_max_consecutive_slots", 999))
    no_first_period_pfx = tuple(raw.pop("no_first_period_prefixes", []))
    no_fri_afternoon_pfx = tuple(raw.pop("no_friday_afternoon_prefixes", []))
    ws_wk_fn_no_overlap = bool(raw.pop("ws_weekly_fortnightly_no_overlap", False))
    max_same_type_ws = int(raw.pop("max_same_type_ws_per_timeslot", 999))
    ext_lunch_days = frozenset(int(d) for d in raw.pop("extended_lunch_days", []))
    ext_lunch_periods = frozenset(int(p) for p in raw.pop("extended_lunch_periods", []))
    no_first_period_days = frozenset(int(d) for d in raw.pop("no_first_period_days", []))
    same_day_lec_consec = bool(raw.pop("same_day_lectures_consecutive", False))

    for prog_str, r in raw.items():
        prog  =  parse_enum(ProgrammeKind, prog_str, field_name = "[programme type] in rules.json")
        by_type[prog]  =  StudentRules(
            horizon_years = to_tuple(r.get("horizon_years", (3, 4))),
            semesters = to_tuple(r.get("semesters", (1, 2))),
            gateway_total_required = int(r.get("gateway_total_required", 8)),
            gateway_max_per_year = int(r.get("gateway_max_per_year", 6)),
            gateway_min_per_year = int(r.get("gateway_min_per_year", 4)),
            gateway_max_per_semester = int(r.get("gateway_max_per_semester", 12)),
            gateway_min_per_semester = int(r.get("gateway_min_per_semester", 2)),
            optional_max_per_year = int(r.get("optional_max_per_year", 4)),
            optional_min_per_year = int(r.get("optional_min_per_year", 2)),
            optional_max_per_semester = int(r.get("optional_max_per_semester", 12)),
            optional_min_per_semester = int(r.get("optional_min_per_semester", 0)),
            courses_max_per_year = int(r.get("courses_max_per_year", 12)),
            courses_min_per_year = int(r.get("courses_min_per_year", 0)),
            courses_max_per_semester = int(r.get("courses_max_per_semester", 12)),
            courses_min_per_semester = int(r.get("courses_min_per_semester", 0)),
            total_credits_per_year = int(r.get("total_credits_per_year", 120)),
            credits_max_per_semester = int(r.get("credits_max_per_semester", 999)),
            credits_min_per_semester = int(r.get("credits_min_per_semester", 0)),
            outside_credits_required_per_year = int(r.get("outside_credits_required_per_year", 0)),
            balanced_credits = bool(r.get("balanced_credits", True)),
            allowed_gateway_ids = maybe_set_str(r.get("allowed_gateway_ids")),
            allowed_optional_ids = maybe_set_str(r.get("allowed_optional_ids")),
            allowed_outside_ids = maybe_set_str(r.get("allowed_outside_ids")),
        )

    return DegreeRules(
        by_type = by_type,
        max_group_size = max_grp,
        global_gateway_per_semester = global_gw,
        global_optional_per_semester = global_opt,
        student_max_daily_gap = student_gap,
        student_max_slots_per_day = student_slots,
        course_max_slots_per_day = course_day,
        lecture_max_per_day = lec_per_day,
        workshop_max_per_day = ws_per_day,
        workshop_after_lecture = ws_after_lec,
        max_concurrent_courses_per_timeslot = max_conc_courses,
        lunch_break_no_class = lunch_no_class,
        student_max_consecutive_slots = max_consec,
        no_first_period_prefixes = no_first_period_pfx,
        no_friday_afternoon_prefixes = no_fri_afternoon_pfx,
        ws_weekly_fortnightly_no_overlap = ws_wk_fn_no_overlap,
        max_same_type_ws_per_timeslot = max_same_type_ws,
        extended_lunch_days = ext_lunch_days,
        extended_lunch_periods = ext_lunch_periods,
        no_first_period_days = no_first_period_days,
        same_day_lectures_consecutive = same_day_lec_consec,
    )


# ── Courses & Components ─────────────────────────────────────────────────────
def load_courses_and_components(courses_csv: Path, components_csv: Path) -> list[Course]:
    course_rows = read_csv(courses_csv)
    comp_rows = read_csv(components_csv)

    comps_by_course: dict[str, list[CourseComponent]]  =  {}
    for i, row in enumerate(comp_rows, start = 1):
        course_id = req(row, "course_id", components_csv, i)
        comp = CourseComponent(
            id = req(row, "id", components_csv, i),
            component_type = parse_enum(ComponentType, req(row, "component_type", components_csv, i), "component_type"),
            frequency = parse_enum(Frequency, get_str(row, "frequency", "weekly"), "frequency"),
            week_pattern = parse_enum(WeekPattern, get_str(row, "week_pattern", "every_week"), "week_pattern"),
            number_per_week = get_int(row, "number_per_week", 1),
            allowed_days = maybe_set_int(split_semicolon(row.get("allowed_days", ""))),
            allowed_periods = maybe_set_int(split_semicolon(row.get("allowed_periods", ""))),
            allowed_timeslots = parse_timeslots(row.get("allowed_timeslots", "")),
            sections_min = get_int(row, "sections_min", 1),
            sections_max = get_int(row, "sections_max", 1),
            section_cap_min = get_int(row, "section_cap_min", 0),
            section_cap_max = get_int(row, "section_cap_max", 999),
        )
        comps_by_course.setdefault(course_id, []).append(comp)

    courses = []
    for i, row in enumerate(course_rows, start = 1):
        cid = req(row, "id", courses_csv, i)
        courses.append(Course(
            id = cid,
            kind = parse_enum(CourseKind, req(row, "kind", courses_csv, i), "kind"),
            credits = int(req(row, "credits", courses_csv, i)),
            name = req(row, "name", courses_csv, i),
            cap_min = get_int(row, "cap_min", 0),
            cap_max = get_int(row, "cap_max", 999),
            allowed_years = maybe_set_int(split_semicolon(row.get("allowed_years", ""))),
            allowed_semesters = maybe_set_int(split_semicolon(row.get("allowed_semesters", ""))),
            forbidden_timeslot_ids = maybe_set_str(split_semicolon(row.get("forbidden_timeslot_ids", ""))),
            components = comps_by_course.get(cid, []),
        ))
        
    return courses


# ── Students ─────────────────────────────────────────────────────────────────
def load_students(path, max_group_size = 999):
    raw = [
        Student(
            id = req(row, "id", path, i),
            programme = parse_enum(ProgrammeKind, req(row, "programme", path, i), "programme"),
            year = get_int(row, "year", 3),
            compulsory_course_ids = split_semicolon(row.get("compulsory_course_ids", "")),
            desired_course_ids = split_semicolon(row.get("desired_course_ids", "")),
            number_students = get_int(row, "number_students", 1),
        )
        for i, row in enumerate(read_csv(path), start = 1)
    ]

    return aggregate_students(raw, max_group_size)


def aggregate_students(students, max_group_size = 999):
    """Merge students with identical (programme, year, compulsory, desired),
    then split any group larger than *max_group_size* into equal-sized subgroups."""
    buckets = {}
    for s in students:
        key = (s.programme, s.year, tuple(s.compulsory_course_ids), tuple(s.desired_course_ids))
        if key in buckets:
            buckets[key] += s.number_students
        else:
            buckets[key] = s.number_students

    aggregated = []
    type_idx = 0
    for (prog, year, comp_ids, des_ids), count in buckets.items():
        if count <= max_group_size:
            # No splitting needed
            aggregated.append(Student(
                id = f"type_{type_idx}",
                programme = prog,
                year = year,
                compulsory_course_ids = list(comp_ids),
                desired_course_ids = list(des_ids),
                number_students = count,
            ))
            type_idx += 1
        else:
            # Split into ceil(count / max_group_size) subgroups of roughly equal size
            n_subs = math.ceil(count / max_group_size)
            base = count // n_subs
            remainder = count % n_subs
            parent_id = f"type_{type_idx}"

            for sub_i in range(n_subs):
                sub_count = base + (1 if sub_i < remainder else 0)
                aggregated.append(Student(
                    id = f"type_{type_idx}_sub{sub_i}",
                    programme = prog,
                    year = year,
                    compulsory_course_ids = list(comp_ids),
                    desired_course_ids = list(des_ids),
                    number_students = sub_count,
                    parent_type = parent_id,
                ))
            type_idx += 1

    return aggregated
