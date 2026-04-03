from dataclasses import dataclass
from ortools.sat.python import cp_model

from data.schema import ComponentType, CourseKind, ProgrammeKind, Instance


@dataclass
class VarSets:
    '''
    open[course_id, component_id, timeslot_key_id] -> BoolVar
    assign[student_id, course_id, component_id, timeslot_key_id] -> BoolVar
    active[course_id, year, semester] -> BoolVar
    take[student_id, course_id, year, semester] -> BoolVar

    NOTE: All students within the same aggregated type share an identical schedule.
    NOTE: take/assign are BoolVar indicating whether the type takes/is-assigned;
    NOTE: number_students is used externally as a weight (objective, enrollment caps).
    '''
    open: dict[tuple[str, str, str], cp_model.IntVar]            # (course_id, component_id, timeslot_key_id) -> BoolVar
    assign: dict[tuple[str, str, str, str], cp_model.IntVar]     # (student_id, course_id, component_id, timeslot_key_id) -> BoolVar
    active: dict[tuple[str, int, int], cp_model.IntVar]          # (course_id, year, semester) -> BoolVar
    take: dict[tuple[str, str, int, int], cp_model.IntVar]       # (student_id, course_id, year, semester) -> BoolVar


def build_variables(model: cp_model.CpModel, inst: Instance):
    open_vars = {}
    assign_vars = {}
    active_vars = {}
    take_vars = {}

    semesters = inst.all_semesters
    years = inst.all_years

    for c in inst.courses:
        # open[course_id, component_id, timeslot_key_id]
        for comp in c.components:
            for k in inst.allowed_timeslot_keys_for_component(c.id, comp.id):
                open_vars[(c.id, comp.id, k.id)] = model.new_bool_var(f"open[{c.id},{comp.id},{k.id}]")

        # active[course_id, year, semester]
        for y in years:
            for sem in semesters:
                # Skip if course not allowed in this year/semester (reducing search space).
                if c.allowed_years is not None and y not in c.allowed_years:
                    continue
                if c.allowed_semesters is not None and sem not in c.allowed_semesters:
                    continue
                active_vars[(c.id, y, sem)] = model.new_bool_var(f"active[{c.id},Y{y},S{sem}]")

    for s in inst.students:
        rule = inst.rules.for_student(s)
        s_years_set = set(inst.years_for_student(s))
        s_sems_set = set(inst.semesters_for_student(s))
        for c in inst.courses:
            # Skip courses the student can never take based on programme / rule restrictions (reducing search space).
            if c.kind == CourseKind.MATH_GW and rule.allowed_gateway_ids is not None and c.id not in rule.allowed_gateway_ids:
                continue
            if c.kind == CourseKind.MATH_OP and rule.allowed_optional_ids is not None and c.id not in rule.allowed_optional_ids:
                continue
            if c.kind == CourseKind.OUTSIDE:
                if s.programme == ProgrammeKind.SINGLE:
                    continue
                if rule.allowed_outside_ids is not None and c.id not in rule.allowed_outside_ids:
                    continue

            # take[student_id, course_id, year, semester]
            for y in inst.years_for_student(s):
                for sem in inst.semesters_for_student(s):
                    # Skip if course not allowed in this year/semester.
                    if c.allowed_years is not None and y not in c.allowed_years:
                        continue
                    if c.allowed_semesters is not None and sem not in c.allowed_semesters:
                        continue
                    
                    take_vars[(s.id, c.id, y, sem)] = model.new_bool_var(f"take[{s.id},{c.id},Y{y},S{sem}]")

            # assign[student_id, course_id, component_id, timeslot_key_id]
            for comp in c.components:
                sectioned = (comp.component_type == ComponentType.WORKSHOP) or (comp.sections_max > 1)

                # For non-sectioned components, we will only generate assign vars for the base slot.
                if not sectioned:
                    continue

                for k in inst.allowed_timeslot_keys_for_component(c.id, comp.id):
                    # Only create assign vars within the student's horizon years/semesters
                    if k.year not in s_years_set or k.semester not in s_sems_set:
                        continue
                    assign_vars[(s.id, c.id, comp.id, k.id)] = model.new_bool_var(f"assign[{s.id},{c.id},{comp.id},{k.id}]")

    return VarSets(open=open_vars, assign=assign_vars, active=active_vars, take=take_vars)
