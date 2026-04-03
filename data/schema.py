from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CourseKind(str, Enum):
    MATH_GW = "gateway"
    MATH_OP = "optional"
    OUTSIDE = "outside"


class ProgrammeKind(str, Enum):
    SINGLE = "single"
    JOINT_CS = "joint_cs"
    JOINT_PHYS = "joint_phys"
    JOINT_ECON = "joint_econ"
    JOINT_BUS = "joint_bus"
    JOINT_PHIL = "joint_phil"


class ComponentType(str, Enum):
    LECTURE = "lecture"
    WORKSHOP = "workshop"


class Frequency(str, Enum):
    WEEKLY = "weekly"
    FORTNIGHTLY = "fortnightly"


class WeekPattern(str, Enum):
    ALL = "every_week"
    ODD = "odd_weeks"
    EVEN = "even_weeks"


@dataclass(frozen=True)
class TimeslotKey:
    year: int
    semester: int
    week_pattern: WeekPattern
    day: int
    period: int

    # For quiker access (avoid repeated calculation for id and base_id each time we use a TimeslotKey)
    def __post_init__(self):
        object.__setattr__(self, '_id',
            f"Y{self.year}_S{self.semester}_{self.week_pattern.value}_D{self.day}_P{self.period}")
        object.__setattr__(self, '_base_id',
            f"Y{self.year}_S{self.semester}_D{self.day}_P{self.period}")

    @property
    def id(self):
        return self._id

    @property
    def base_id(self):
        """Collapse week_pattern."""
        return self._base_id


@dataclass(frozen=True)
class CourseComponent:
    id: str
    component_type: ComponentType
    frequency: Frequency = Frequency.WEEKLY
    week_pattern: WeekPattern = WeekPattern.ALL
    number_per_week: int = 1

    allowed_days: Optional[set[int]] = None
    allowed_periods: Optional[set[int]] = None
    allowed_timeslots: Optional[set[tuple[int, int]]] = None
    sections_min: int = 1
    sections_max: int = 1
    section_cap_min: int = 0
    section_cap_max: int = 999


@dataclass(frozen=True)
class Course:
    id: str
    kind: CourseKind
    credits: int
    name: str
    components: list = field(default_factory=list)

    cap_max: int = 999
    cap_min: int = 0
    allowed_years: Optional[set[int]] = None
    allowed_semesters: Optional[set[int]] = None

    forbidden_timeslot_ids: Optional[set[str]] = None

    def component_ids(self):
        return [comp.id for comp in self.components]


@dataclass(frozen=True)
class Student:
    id: str
    programme: ProgrammeKind
    year: int = 3

    compulsory_course_ids: list = field(default_factory=list)
    desired_course_ids: list = field(default_factory=list)

    # Aggregated count of students with same programme/year/compulsory/desired courses
    number_students: int = 1

    # If this student was split from a larger aggregated group, parent_type
    # records the original type id shared by all sibling subgroups.
    parent_type: Optional[str] = None


@dataclass(frozen=True)
class StudentRules:
    horizon_years: tuple = (3, 4)
    semesters: tuple = (1, 2)

    gateway_total_required: int = 8
    gateway_max_per_year: int = 6
    gateway_min_per_year: int = 4
    gateway_max_per_semester: int = 12
    gateway_min_per_semester: int = 2

    optional_max_per_year: int = 4
    optional_min_per_year: int = 2
    optional_max_per_semester: int = 12
    optional_min_per_semester: int = 0

    courses_max_per_year: int = 12
    courses_min_per_year: int = 0
    courses_max_per_semester: int = 12
    courses_min_per_semester: int = 0

    total_credits_per_year: int = 120
    credits_max_per_semester: int = 999
    credits_min_per_semester: int = 0
    outside_credits_required_per_year: int = 0

    balanced_credits: bool = True

    allowed_gateway_ids: Optional[set[str]] = None
    allowed_optional_ids: Optional[set[str]] = None
    allowed_outside_ids: Optional[set[str]] = None


@dataclass(frozen=True)
class DegreeRules:
    by_type: dict = field(default_factory=dict)
    max_group_size: int = 999
    global_gateway_per_semester: int = 4
    global_optional_per_semester: int = 2
    student_max_daily_gap: int = 999
    student_max_slots_per_day: int = 999
    course_max_slots_per_day: int = 999
    lecture_max_per_day: int = 999
    workshop_max_per_day: int = 999
    workshop_after_lecture: bool = False
    max_concurrent_courses_per_timeslot: int = 999
    lunch_break_no_class: bool = False
    student_max_consecutive_slots: int = 999
    no_first_period_prefixes: tuple = ()
    no_friday_afternoon_prefixes: tuple = ()
    ws_weekly_fortnightly_no_overlap: bool = False
    max_same_type_ws_per_timeslot: int = 999
    extended_lunch_days: frozenset = frozenset()
    extended_lunch_periods: frozenset = frozenset()
    no_first_period_days: frozenset = frozenset()
    same_day_lectures_consecutive: bool = False

    def for_student(self, s: Student):
        if s.programme not in self.by_type:
            raise KeyError(f"Missing StudentRules for programme={s.programme}")
        
        return self.by_type[s.programme]


@dataclass(frozen=True)
class Instance:
    rules: DegreeRules
    timeslot_keys_list: list[TimeslotKey] = field(default_factory=list)
    courses: list[Course] = field(default_factory=list)
    students: list[Student] = field(default_factory=list)

    slot_start_minutes: int = 540    # default 9:00
    slot_duration_minutes: int = 60  # default 1h

    # For quicker access (avoid repeated lookups and calculations each time we need these)
    def __post_init__(self):
        object.__setattr__(self, '_course_by_id',
            {c.id: c for c in self.courses})
        object.__setattr__(self, '_key_by_id',
            {k.id: k for k in self.timeslot_keys_list})
        object.__setattr__(self, '_years',
            sorted({k.year for k in self.timeslot_keys_list}))
        object.__setattr__(self, '_semesters',
            sorted({k.semester for k in self.timeslot_keys_list}))
        object.__setattr__(self, '_course_ids',
            [c.id for c in self.courses])
        object.__setattr__(self, '_gateway_course_ids',
            [c.id for c in self.courses if c.kind == CourseKind.MATH_GW])
        object.__setattr__(self, '_optional_course_ids',
            [c.id for c in self.courses if c.kind == CourseKind.MATH_OP])
        object.__setattr__(self, '_outside_course_ids',
            [c.id for c in self.courses if c.kind == CourseKind.OUTSIDE])

        allowed = {}
        for c in self.courses:
            for comp in c.components:
                allowed[(c.id, comp.id)] = self.compute_allowed_keys(c, comp)
        object.__setattr__(self, '_allowed_keys', allowed)


    @property
    def course_by_id(self):
        return self._course_by_id

    @property
    def timeslot_key_by_id(self):
        return self._key_by_id

    @property
    def all_years(self):
        return self._years

    @property
    def all_semesters(self):
        return self._semesters

    @property
    def course_ids(self):
        return self._course_ids

    @property
    def gateway_course_ids(self):
        return self._gateway_course_ids

    @property
    def optional_course_ids(self):
        return self._optional_course_ids

    @property
    def outside_course_ids(self):
        return self._outside_course_ids

    def years_for_student(self, s):
        r = self.rules.for_student(s)
        y0, y1 = r.horizon_years
        return list(range(y0, y1 + 1))

    def semesters_for_student(self, s):
        r = self.rules.for_student(s)
        s0, s1 = r.semesters
        return list(range(s0, s1 + 1))

    def allowed_timeslot_keys_for_component(self, course_id, comp_id):
        """Return pre-computed allowed TimeslotKeys for a component."""
        return self._allowed_keys[(course_id, comp_id)]

    def format_period_time(self, period):
        """Convert period index to 'HH:MM-HH:MM' range string."""
        s = self.slot_start_minutes + period * self.slot_duration_minutes
        e = s + self.slot_duration_minutes
        return f"{s // 60}:{s % 60:02d}-{e // 60}:{e % 60:02d}"

    def format_period_start(self, period):
        """Convert period index to 'HH:MM' string."""
        s = self.slot_start_minutes + period * self.slot_duration_minutes
        return f"{s // 60}:{s % 60:02d}"


    # ── Internal helper ─────────────────────────────────────────────────
    def compute_allowed_keys(self, course, comp):
        """Filter timeslot keys for one (course, component) pair — single pass."""
        if comp.frequency == Frequency.FORTNIGHTLY and comp.week_pattern == WeekPattern.ALL:
            raise ValueError(
                f"Course {course.id} component {comp.id} is fortnightly but week_pattern=ALL"
            )
        if comp.frequency == Frequency.WEEKLY and comp.week_pattern != WeekPattern.ALL:
            raise ValueError(
                f"Course {course.id} component {comp.id} is weekly but week_pattern is not ALL"
            )

        c_years = course.allowed_years
        c_sems  = course.allowed_semesters
        c_forb  = course.forbidden_timeslot_ids
        cp_days = comp.allowed_days
        cp_pers = comp.allowed_periods
        cp_ts   = comp.allowed_timeslots
        wp      = comp.week_pattern

        # Compute lunch-break forbidden periods (if enabled).
        # Only apply to non-outside courses — outside courses have fixed
        # schedules from other departments that we cannot move.
        lunch_periods = set()
        if self.rules.lunch_break_no_class and course.kind != CourseKind.OUTSIDE:
            lunch_start = 12 * 60   # 12:00
            lunch_end   = 13 * 60   # 13:00
            max_period = (18 * 60 - self.slot_start_minutes) // self.slot_duration_minutes
            for p in range(max_period):
                p_start = self.slot_start_minutes + p * self.slot_duration_minutes
                p_end   = p_start + self.slot_duration_minutes
                if p_start < lunch_end and p_end > lunch_start:
                    lunch_periods.add(p)

        # Prefix-based period restrictions (applied at variable creation to
        # keep the model small and avoid post-hoc zero-forcing).
        no_first_period = bool(
            self.rules.no_first_period_prefixes
            and course.id.startswith(self.rules.no_first_period_prefixes)
        )
        no_fri_afternoon = bool(
            self.rules.no_friday_afternoon_prefixes
            and course.id.startswith(self.rules.no_friday_afternoon_prefixes)
        )

        result = []
        for k in self.timeslot_keys_list:
            if k.week_pattern != wp:
                continue
            if c_years is not None and k.year not in c_years:
                continue
            if c_sems is not None and k.semester not in c_sems:
                continue
            if c_forb is not None and k.id in c_forb:
                continue
            if k.period in lunch_periods:
                continue
            if no_first_period and k.period == 0:
                continue
            if (self.rules.no_first_period_days
                    and course.kind != CourseKind.OUTSIDE
                    and k.period == 0
                    and k.day in self.rules.no_first_period_days):
                continue
            if no_fri_afternoon and k.day == 4 and k.period >= 4:
                continue
            if (self.rules.extended_lunch_days
                    and course.kind != CourseKind.OUTSIDE
                    and k.day in self.rules.extended_lunch_days
                    and k.period in self.rules.extended_lunch_periods):
                continue
            # allowed_timeslots takes precedence over allowed_days/periods
            if cp_ts is not None:
                if (k.day, k.period) not in cp_ts:
                    continue
            else:
                if cp_days is not None and k.day not in cp_days:
                    continue
                if cp_pers is not None and k.period not in cp_pers:
                    continue
            result.append(k)

        return result

    # Just a sanity check our instance is well-formed :)   (a sad story haha)
    def validate(self):
        """Run all validation checks on the instance."""
        self.validate_structure()
        self.validate_timeslot_coverage()
        self.validate_rules_references()
        self.validate_rules_consistency()
        self.validate_rules_feasibility()
        self.validate_global_offering_feasibility()
        self.validate_students_feasibility()
        self.validate_compulsory_reachability()

    def validate_structure(self):
        """Check uniqueness, basic format, components, students."""
        assert_unique([k.id for k in self.timeslot_keys_list], "TimeslotKey.id must be unique")
        assert_unique([c.id for c in self.courses], "Course.id must be unique")
        assert_unique([s.id for s in self.students], "Student.id must be unique")
        course_set = set(self.course_ids)

        for c in self.courses:
            if c.credits <= 0:
                raise ValueError(f"Course {c.id} credits must be positive, got {c.credits}")
            if c.cap_min < 0 or c.cap_max < 0 or c.cap_min > c.cap_max:
                raise ValueError(f"Course {c.id} invalid caps: cap_min={c.cap_min}, cap_max={c.cap_max}")
            
            assert_unique(c.component_ids(), f"Course {c.id} component.id must be unique")

            for comp in c.components:
                if comp.number_per_week <= 0:
                    raise ValueError(f"Course {c.id} component {comp.id}: number_per_week must be >= 1")
                if comp.frequency == Frequency.WEEKLY and comp.week_pattern != WeekPattern.ALL:
                    raise ValueError(f"Course {c.id} component {comp.id}: weekly must use week_pattern=ALL")
                if comp.frequency == Frequency.FORTNIGHTLY and comp.week_pattern == WeekPattern.ALL:
                    raise ValueError(f"Course {c.id} component {comp.id}: fortnightly must use week_pattern ODD or EVEN")
                if comp.sections_min < 0 or comp.sections_max < 0 or comp.sections_min > comp.sections_max:
                    raise ValueError(f"Course {c.id} component {comp.id}: invalid sections_min/max ({comp.sections_min}, {comp.sections_max})")
                if comp.section_cap_min < 0 or comp.section_cap_max < 0 or comp.section_cap_min > comp.section_cap_max:
                    raise ValueError(f"Course {c.id} component {comp.id}: invalid section_cap_min/max ({comp.section_cap_min}, {comp.section_cap_max})")
                if comp.component_type == ComponentType.LECTURE:
                    if comp.sections_min != 1 or comp.sections_max != 1:
                        raise ValueError(f"Course {c.id} component {comp.id}: lectures should have sections_min=sections_max=1")

        for s in self.students:
            for cid in s.compulsory_course_ids:
                if cid not in course_set:
                    raise ValueError(f"Student {s.id} compulsory_course {cid} not found")
            for cid in s.desired_course_ids:
                if cid not in course_set:
                    raise ValueError(f"Student {s.id} desired_course {cid} not found")

    def validate_timeslot_coverage(self):
        """
        Ensure component allowed_days/periods exist in timeslot config:
        - every component has at least one timeslot key
        - and every course is fully schedulable (no component with zero keys).
        """
        active_days = sorted({k.day for k in self.timeslot_keys_list})
        active_periods = sorted({k.period for k in self.timeslot_keys_list})
        active_years = sorted({k.year for k in self.timeslot_keys_list})
        active_semesters = sorted({k.semester for k in self.timeslot_keys_list})
        day_set = set(active_days)
        period_set = set(active_periods)
        year_set = set(active_years)
        semester_set = set(active_semesters)

        for c in self.courses:
            # Check course-level allowed_years / allowed_semesters reference valid values
            if c.allowed_years is not None:
                bad = c.allowed_years - year_set
                if bad:
                    raise ValueError(
                        f"Course {c.id}: allowed_years {sorted(c.allowed_years)} "
                        f"references years {sorted(bad)} not in timeslot_config "
                        f"(active years: {active_years})")
                
            if c.allowed_semesters is not None:
                bad = c.allowed_semesters - semester_set
                if bad:
                    raise ValueError(
                        f"Course {c.id}: allowed_semesters {sorted(c.allowed_semesters)} "
                        f"references semesters {sorted(bad)} not in timeslot_config "
                        f"(active semesters: {active_semesters})")

            for comp in c.components:
                # Check component allowed_timeslots within active day-period pairs
                if comp.allowed_timeslots is not None:
                    active_pairs = {(k.day, k.period) for k in self.timeslot_keys_list}
                    bad = comp.allowed_timeslots - active_pairs
                    if bad:
                        raise ValueError(
                            f"Course {c.id} component {comp.id}: allowed_timeslots "
                            f"references day:period pair(s) {sorted(bad)} not in "
                            f"timeslot_config")
                else:
                    # Check component allowed_days within active days
                    if comp.allowed_days is not None:
                        bad = comp.allowed_days - day_set
                        if bad:
                            raise ValueError(
                                f"Course {c.id} component {comp.id}: allowed_days "
                                f"{sorted(comp.allowed_days)} references day(s) "
                                f"{sorted(bad)} not in timeslot_config "
                                f"(active_days: {active_days})")

                    # Check component allowed_periods within active periods
                    if comp.allowed_periods is not None:
                        bad = comp.allowed_periods - period_set
                        if bad:
                            raise ValueError(
                                f"Course {c.id} component {comp.id}: allowed_periods "
                                f"{sorted(comp.allowed_periods)} references period(s) "
                                f"{sorted(bad)} not in timeslot_config "
                                f"(active_periods: {active_periods})")

                # Check that the component actually has at least one timeslot key
                keys = self.allowed_timeslot_keys_for_component(c.id, comp.id)
                if len(keys) == 0:
                    raise ValueError(
                        f"Course {c.id} component {comp.id} "
                        f"({comp.component_type.value}, {comp.frequency.value}, "
                        f"wp={comp.week_pattern.value}): "
                        f"0 timeslot keys after filtering — the component is "
                        f"unschedulable. Check allowed_timeslots={comp.allowed_timeslots}, "
                        f"allowed_days={comp.allowed_days}, "
                        f"allowed_periods={comp.allowed_periods}, "
                        f"course allowed_years={c.allowed_years}, "
                        f"allowed_semesters={c.allowed_semesters}, "
                        f"forbidden_timeslot_ids count="
                        f"{len(c.forbidden_timeslot_ids) if c.forbidden_timeslot_ids else 0}")

                # Check number_per_week does not exceed available distinct
                # (day, period) slots (for weekly) or available keys (for fortnightly)
                if comp.frequency == Frequency.WEEKLY:
                    distinct_slots = len({(k.day, k.period) for k in keys
                                          if k.year == keys[0].year
                                          and k.semester == keys[0].semester})
                else:  # fortnightly
                    distinct_slots = len({(k.day, k.period) for k in keys
                                          if k.year == keys[0].year
                                          and k.semester == keys[0].semester})
                    
                needed = comp.number_per_week * comp.sections_min
                if needed > distinct_slots:
                    raise ValueError(
                        f"Course {c.id} component {comp.id}: needs "
                        f"number_per_week({comp.number_per_week}) × "
                        f"sections_min({comp.sections_min}) = {needed} distinct "
                        f"slots, but only {distinct_slots} available after filtering")

    def validate_rules_references(self):
        """Check that rules reference only known course IDs."""
        course_set = set(self.course_ids)
        for prog, rule in self.rules.by_type.items():
            if rule.allowed_gateway_ids is not None:
                unknown = set(rule.allowed_gateway_ids) - course_set
                if unknown:
                    raise ValueError(f"Rule {prog} allowed_gateway_ids unknown: {sorted(unknown)}")
                
            if rule.allowed_optional_ids is not None:
                unknown = set(rule.allowed_optional_ids) - course_set
                if unknown:
                    raise ValueError(f"Rule {prog} allowed_optional_ids unknown: {sorted(unknown)}")
                
            if rule.allowed_outside_ids is not None:
                unknown = set(rule.allowed_outside_ids) - course_set
                if unknown:
                    raise ValueError(f"Rule {prog} allowed_outside_ids unknown: {sorted(unknown)}")

    def validate_rules_consistency(self):
        """Check min ≤ max bound constraints within each rule."""
        for prog, rule in self.rules.by_type.items():
            if rule.gateway_min_per_year > rule.gateway_max_per_year:
                raise ValueError(f"Rule {prog}: gateway_min_per_year ({rule.gateway_min_per_year}) > gateway_max_per_year ({rule.gateway_max_per_year})")
            if rule.gateway_min_per_semester > rule.gateway_max_per_semester:
                raise ValueError(f"Rule {prog}: gateway_min_per_semester ({rule.gateway_min_per_semester}) > gateway_max_per_semester ({rule.gateway_max_per_semester})")
            if rule.optional_min_per_year > rule.optional_max_per_year:
                raise ValueError(f"Rule {prog}: optional_min_per_year ({rule.optional_min_per_year}) > optional_max_per_year ({rule.optional_max_per_year})")
            if rule.optional_min_per_semester > rule.optional_max_per_semester:
                raise ValueError(f"Rule {prog}: optional_min_per_semester ({rule.optional_min_per_semester}) > optional_max_per_semester ({rule.optional_max_per_semester})")
            if rule.courses_min_per_year > rule.courses_max_per_year:
                raise ValueError(f"Rule {prog}: courses_min_per_year ({rule.courses_min_per_year}) > courses_max_per_year ({rule.courses_max_per_year})")
            if rule.courses_min_per_semester > rule.courses_max_per_semester:
                raise ValueError(f"Rule {prog}: courses_min_per_semester ({rule.courses_min_per_semester}) > courses_max_per_semester ({rule.courses_max_per_semester})")
            if rule.credits_min_per_semester > rule.credits_max_per_semester:
                raise ValueError(f"Rule {prog}: credits_min_per_semester ({rule.credits_min_per_semester}) > credits_max_per_semester ({rule.credits_max_per_semester})")

    def validate_rules_feasibility(self):
        """Catch infeasibility before solving — rule-level checks."""
        ts_year_set = set(self.all_years)
        ts_sem_set = set(self.all_semesters)

        for prog, rule in self.rules.by_type.items():
            y0, y1 = rule.horizon_years
            num_years = y1 - y0 + 1
            s0, s1 = rule.semesters
            num_sems = s1 - s0 + 1

            # Horizon years/semesters must exist in timeslot config
            horizon_years = set(range(y0, y1 + 1))
            bad_years = horizon_years - ts_year_set
            if bad_years:
                raise ValueError(
                    f"Rule {prog}: horizon_years {sorted(horizon_years)} contains years "
                    f"{sorted(bad_years)} not in timeslot_config (available: {sorted(ts_year_set)})")
            rule_sems = set(range(s0, s1 + 1))
            bad_sems = rule_sems - ts_sem_set
            if bad_sems:
                raise ValueError(
                    f"Rule {prog}: semesters {sorted(rule_sems)} contains semesters "
                    f"{sorted(bad_sems)} not in timeslot_config (available: {sorted(ts_sem_set)})")

            if rule.balanced_credits and num_sems > 1:
                if rule.total_credits_per_year % num_sems != 0:
                    raise ValueError(
                        f"Rule {prog}: balanced_credits=True but total_credits_per_year="
                        f"{rule.total_credits_per_year} is not divisible by {num_sems} semesters")

            avail_gw = [c for c in self.courses if c.kind == CourseKind.MATH_GW]
            if rule.allowed_gateway_ids is not None:
                avail_gw = [c for c in avail_gw if c.id in rule.allowed_gateway_ids]

            avail_opt = [c for c in self.courses if c.kind == CourseKind.MATH_OP]
            if rule.allowed_optional_ids is not None:
                avail_opt = [c for c in avail_opt if c.id in rule.allowed_optional_ids]

            avail_out = []
            if prog != ProgrammeKind.SINGLE:
                avail_out = [c for c in self.courses if c.kind == CourseKind.OUTSIDE]
                if rule.allowed_outside_ids is not None:
                    avail_out = [c for c in avail_out if c.id in rule.allowed_outside_ids]
            avail_all = avail_gw + avail_opt + avail_out

            if len(avail_gw) < rule.gateway_total_required:
                raise ValueError(
                    f"Rule {prog}: gateway_total_required={rule.gateway_total_required} "
                    f"but only {len(avail_gw)} gateway courses available (each taken at most once)")
            
            if rule.gateway_total_required > rule.gateway_max_per_year * num_years:
                raise ValueError(
                    f"Rule {prog}: gateway_total_required={rule.gateway_total_required} "
                    f"exceeds gateway_max_per_year ({rule.gateway_max_per_year}) × {num_years} years = "
                    f"{rule.gateway_max_per_year * num_years}")
            
            if rule.gateway_min_per_year * num_years > len(avail_gw):
                raise ValueError(
                    f"Rule {prog}: gateway_min_per_year={rule.gateway_min_per_year} × {num_years} years = "
                    f"{rule.gateway_min_per_year * num_years} but only {len(avail_gw)} gateway courses available")
            
            if rule.outside_credits_required_per_year > 0:
                total_out_credits = sum(c.credits for c in avail_out)
                total_out_needed = rule.outside_credits_required_per_year * num_years
                if total_out_credits < total_out_needed:
                    raise ValueError(
                        f"Rule {prog}: outside_credits_required_per_year={rule.outside_credits_required_per_year} "
                        f"× {num_years} years = {total_out_needed} credits needed, "
                        f"but only {total_out_credits} credits available from "
                        f"{len(avail_out)} outside courses {[c.id for c in avail_out]}")
                
            total_avail_credits = sum(c.credits for c in avail_all)
            total_needed_credits = rule.total_credits_per_year * num_years
            if total_avail_credits < total_needed_credits:
                raise ValueError(
                    f"Rule {prog}: total_credits_per_year={rule.total_credits_per_year} "
                    f"× {num_years} years = {total_needed_credits} credits needed, "
                    f"but only {total_avail_credits} credits available from "
                    f"{len(avail_all)} courses (each taken at most once)")
            
            gw_sem_min_sum = rule.gateway_min_per_semester * num_sems
            if gw_sem_min_sum > rule.gateway_max_per_year and rule.gateway_min_per_semester > 0:
                raise ValueError(
                    f"Rule {prog}: gateway_min_per_semester ({rule.gateway_min_per_semester}) "
                    f"× {num_sems} semesters = {gw_sem_min_sum} > gateway_max_per_year ({rule.gateway_max_per_year})")
            
            opt_sem_min_sum = rule.optional_min_per_semester * num_sems
            if opt_sem_min_sum > rule.optional_max_per_year and rule.optional_min_per_semester > 0:
                raise ValueError(
                    f"Rule {prog}: optional_min_per_semester ({rule.optional_min_per_semester}) "
                    f"× {num_sems} semesters = {opt_sem_min_sum} > optional_max_per_year ({rule.optional_max_per_year})")
            
            if rule.credits_max_per_semester < 999:
                if rule.credits_max_per_semester * num_sems < rule.total_credits_per_year:
                    raise ValueError(
                        f"Rule {prog}: credits_max_per_semester ({rule.credits_max_per_semester}) "
                        f"× {num_sems} semesters = {rule.credits_max_per_semester * num_sems} "
                        f"< total_credits_per_year ({rule.total_credits_per_year})")
                
            if rule.credits_min_per_semester > 0:
                if rule.credits_min_per_semester * num_sems > rule.total_credits_per_year:
                    raise ValueError(
                        f"Rule {prog}: credits_min_per_semester ({rule.credits_min_per_semester}) "
                        f"× {num_sems} semesters = {rule.credits_min_per_semester * num_sems} "
                        f"> total_credits_per_year ({rule.total_credits_per_year})")
                

    def validate_global_offering_feasibility(self):
        gw_per_sem = self.rules.global_gateway_per_semester
        opt_per_sem = self.rules.global_optional_per_semester
        num_sems = len(self.all_semesters)

        gw_courses = [c for c in self.courses if c.kind == CourseKind.MATH_GW]
        opt_courses = [c for c in self.courses if c.kind == CourseKind.MATH_OP]

        # Global check: total courses must be enough to fill all semesters
        # (each course used at most once across semesters due to C1)
        if len(gw_courses) < gw_per_sem * num_sems:
            raise ValueError(
                f"Global offering: global_gateway_per_semester={gw_per_sem} × "
                f"{num_sems} semesters = {gw_per_sem * num_sems} gateway courses "
                f"needed, but only {len(gw_courses)} gateway courses exist")

        if len(opt_courses) < opt_per_sem * num_sems:
            raise ValueError(
                f"Global offering: global_optional_per_semester={opt_per_sem} × "
                f"{num_sems} semesters = {opt_per_sem * num_sems} optional courses "
                f"needed, but only {len(opt_courses)} optional courses exist")

        # Per-semester check: enough candidates per semester
        for sem in self.all_semesters:
            gw_cands = [c for c in gw_courses
                        if c.allowed_semesters is None or sem in c.allowed_semesters]
            if len(gw_cands) < gw_per_sem:
                raise ValueError(
                    f"Global offering: semester {sem} needs {gw_per_sem} gateway "
                    f"courses but only {len(gw_cands)} gateway courses allow "
                    f"that semester (check allowed_semesters in courses.csv)")

            opt_cands = [c for c in opt_courses
                         if c.allowed_semesters is None or sem in c.allowed_semesters]
            if len(opt_cands) < opt_per_sem:
                raise ValueError(
                    f"Global offering: semester {sem} needs {opt_per_sem} optional "
                    f"courses but only {len(opt_cands)} optional courses allow "
                    f"that semester (check allowed_semesters in courses.csv)")

                    
    def validate_students_feasibility(self):
        """Per-student feasibility checks."""
        for s in self.students:
            rule = self.rules.for_student(s)
            for cid in s.compulsory_course_ids:
                c = self.course_by_id.get(cid)
                if c is None:
                    continue

                if c.kind == CourseKind.MATH_GW and rule.allowed_gateway_ids is not None:
                    if cid not in rule.allowed_gateway_ids:
                        raise ValueError(
                            f"Student {s.id}: compulsory gateway course {cid} not in "
                            f"allowed_gateway_ids for programme {s.programme}")
                    
                if c.kind == CourseKind.MATH_OP and rule.allowed_optional_ids is not None:
                    if cid not in rule.allowed_optional_ids:
                        raise ValueError(
                            f"Student {s.id}: compulsory optional course {cid} not in "
                            f"allowed_optional_ids for programme {s.programme}")
                    
                if c.kind == CourseKind.OUTSIDE:
                    if s.programme == ProgrammeKind.SINGLE:
                        raise ValueError(
                            f"Student {s.id}: compulsory outside course {cid} "
                            f"but programme is SINGLE (outside courses blocked)")
                    
                    if rule.allowed_outside_ids is not None and cid not in rule.allowed_outside_ids:
                        raise ValueError(
                            f"Student {s.id}: compulsory outside course {cid} not in "
                            f"allowed_outside_ids for programme {s.programme}")

            s_years = self.years_for_student(s)
            s_sems = self.semesters_for_student(s)
            avail_for_student = []
            for c in self.courses:
                if c.kind == CourseKind.MATH_GW and rule.allowed_gateway_ids is not None and c.id not in rule.allowed_gateway_ids:
                    continue
                if c.kind == CourseKind.MATH_OP and rule.allowed_optional_ids is not None and c.id not in rule.allowed_optional_ids:
                    continue
                if c.kind == CourseKind.OUTSIDE:
                    if s.programme == ProgrammeKind.SINGLE:
                        continue
                    if rule.allowed_outside_ids is not None and c.id not in rule.allowed_outside_ids:
                        continue

                reachable = False
                for y in s_years:
                    if c.allowed_years is not None and y not in c.allowed_years:
                        continue
                    for sem in s_sems:
                        if c.allowed_semesters is not None and sem not in c.allowed_semesters:
                            continue
                        reachable = True
                        break
                    if reachable:
                        break

                if reachable:
                    avail_for_student.append(c)

            total_avail = sum(c.credits for c in avail_for_student)
            total_need = rule.total_credits_per_year * len(s_years)
            if total_avail < total_need:
                raise ValueError(
                    f"Student {s.id} ({s.programme}): needs {rule.total_credits_per_year} × "
                    f"{len(s_years)} years = {total_need} credits, "
                    f"but only {total_avail} credits from {len(avail_for_student)} reachable courses")


    def validate_compulsory_reachability(self):
        """
        Ensure every compulsory course for every student type is actually reachable: 
        - the course must have timeslot keys in at least one (year, semester) the student can use
        - and every component of the course must also have keys in that (year, semester).
        """
        course_by_id = self.course_by_id

        for s in self.students:
            rule = self.rules.for_student(s)
            s_years = self.years_for_student(s)
            s_sems = self.semesters_for_student(s)

            for cid in s.compulsory_course_ids:
                c = course_by_id.get(cid)
                if c is None:
                    continue

                # A compulsory course needs at least one (year, sem) where ALL of its components have timeslot keys.
                viable_ys = []
                for y in s_years:
                    if c.allowed_years is not None and y not in c.allowed_years:
                        continue
                    for sem in s_sems:
                        if c.allowed_semesters is not None and sem not in c.allowed_semesters:
                            continue
                        all_comps_ok = True
                        for comp in c.components:
                            keys_in_ys = [
                                k for k in self.allowed_timeslot_keys_for_component(cid, comp.id)
                                if k.year == y and k.semester == sem
                            ]
                            if not keys_in_ys:
                                all_comps_ok = False
                                break
                        if all_comps_ok:
                            viable_ys.append((y, sem))

                if not viable_ys:
                    # Build a helpful message showing which components lacked keys
                    problems = []
                    for comp in c.components:
                        comp_keys = self.allowed_timeslot_keys_for_component(cid, comp.id)
                        if not comp_keys:
                            problems.append(f"{comp.id}(0 keys total)")
                        else:
                            ys_with_keys = sorted({(k.year, k.semester) for k in comp_keys})
                            problems.append(
                                f"{comp.id}(keys only in "
                                f"{['Y'+str(y)+'_S'+str(s) for y,s in ys_with_keys]})")
                            
                    raise ValueError(
                        f"Student {s.id} ({s.programme.value}): compulsory course "
                        f"{cid} has no viable (year, semester) where all components "
                        f"are schedulable. Student years={s_years}, sems={s_sems}. "
                        f"Component issues: {'; '.join(problems)}")

            # Also check: for joint students, outside_credits_required_per_year
            # must be achievable with courses that are actually schedulable
            if rule.outside_credits_required_per_year > 0:
                for y in s_years:
                    schedulable_out_credits = 0
                    for c in self.courses:
                        if c.kind != CourseKind.OUTSIDE:
                            continue
                        if s.programme == ProgrammeKind.SINGLE:
                            continue
                        if rule.allowed_outside_ids is not None and c.id not in rule.allowed_outside_ids:
                            continue

                        # Check if any semester works for this course this year
                        for sem in s_sems:
                            if c.allowed_years is not None and y not in c.allowed_years:
                                continue
                            if c.allowed_semesters is not None and sem not in c.allowed_semesters:
                                continue
                            all_ok = True
                            for comp in c.components:
                                keys_in_ys = [
                                    k for k in self.allowed_timeslot_keys_for_component(c.id, comp.id)
                                    if k.year == y and k.semester == sem
                                ]
                                if not keys_in_ys:
                                    all_ok = False
                                    break
                            if all_ok:
                                schedulable_out_credits += c.credits
                                break

                    if schedulable_out_credits < rule.outside_credits_required_per_year:
                        raise ValueError(
                            f"Student {s.id} ({s.programme.value}): in year {y}, "
                            f"outside_credits_required={rule.outside_credits_required_per_year} "
                            f"but only {schedulable_out_credits} credits from schedulable "
                            f"outside courses (some courses have components with 0 timeslot keys)")


# Tools ----------------------------------------------------------------

def assert_unique(items, msg):
    items = list(items)
    if len(items) != len(set(items)):
        raise ValueError(msg)