"""Objective function for the timetabling model.

Weighted combination (minimised):
  + Bonus   : students taking their desired courses (pathway incentive)
  - Penalty : per-student per-base-slot timetable conflicts
              (lecture-lecture / lecture-workshop / workshop-workshop)
  - Penalty : each course activation (tie-breaking towards fewer activations)
"""
from collections import defaultdict
from ortools.sat.python import cp_model

from data.schema import ComponentType, WeekPattern, Instance
from model.variables import VarSets
from model.utils import is_sectioned, bool_and, patterns_overlap
from config.objective_config import load_objective_config


def add_objective(model: cp_model.CpModel, inst: Instance, vs: VarSets):
    cfg = load_objective_config()
    penalties = []
    bonuses = []

    key_by_id  = inst.timeslot_key_by_id
    comp_by_id = {(c.id, comp.id): comp for c in inst.courses for comp in c.components}
    course_by_id = inst.course_by_id
    count_of = {s.id: s.number_students for s in inst.students}


    # ── BONUS: encourage students to take desired courses ────────────────
    # take is BoolVar; weight by number_students for proper scaling.
    desired_by_student = {
        s.id: set(s.desired_course_ids) & set(course_by_id)
        for s in inst.students
    }
    for (sid, cid, y, sem), tv in vs.take.items():
        if cid in desired_by_student.get(sid, set()):
            bonuses.append(cfg.desire_bonus_weight * count_of[sid] * tv)


    # ── SMALL PENALTY: discourage unnecessary course activations ─────────
    for av in vs.active.values():
        penalties.append(cfg.activation_penalty * av)


    # ── CONFLICT PENALTY ──────────────────────────────────────────────────
    #
    # All students in a type share the same schedule.  Attendance per
    # (student_type, base_slot) is a BoolVar: take AND open for non-
    # sectioned components, assign for sectioned.
    # Penalty for each pairwise conflict is weighted by number_students
    # since every student in the type experiences the clash.

    # Index non-sectioned open vars by (course, year, semester)
    open_nonsect_by_cys = defaultdict(list)
    for (cid, compid, kid), ov in vs.open.items():
        comp = comp_by_id[(cid, compid)]
        if is_sectioned(comp):
            continue
        kk = key_by_id[kid]
        open_nonsect_by_cys[(cid, kk.year, kk.semester)].append(
            (compid, kid, kk.base_id, ov, comp.component_type, kk.week_pattern)
        )

    # Build per-(student_type, base) attendance BoolVars
    stu_attend = defaultdict(list)  # (sid, base) -> [(BoolVar, ComponentType, WeekPattern)]

    # Non-sectioned: attendance = take AND open
    for (sid, cid, y, sem), tv in vs.take.items():
        for compid, kid, base, ov, comp_type, wp in open_nonsect_by_cys.get((cid, y, sem), []):
            att = bool_and(model, tv, ov, f"att[{sid},{cid},{compid},{kid}]")
            stu_attend[(sid, base)].append((att, comp_type, wp))

    # Sectioned: attendance = assign (BoolVar directly)
    for (sid, cid, compid, kid), av in vs.assign.items():
        comp = comp_by_id[(cid, compid)]
        kk = key_by_id[kid]
        stu_attend[(sid, kk.base_id)].append(
            (av, comp.component_type, kk.week_pattern)
        )

    # Pairwise conflict penalties, weighted by number_students
    for (sid, base), entries in stu_attend.items():
        if len(entries) >= 2:
            add_conflict_penalty(model, cfg, penalties, sid, base, entries,
                                 weight=count_of[sid])


    # ── Assemble and minimise objective ──────────────────────────────────
    obj = (sum(penalties) if penalties else 0) - (sum(bonuses) if bonuses else 0)
    model.minimize(obj)


# ── Helpers ──────────────────────────────────────────────────────────────────

def add_conflict_penalty(model: cp_model.CpModel, cfg, penalties, sid, base, entries,
                         weight=1):
    """Penalise a timetable conflict at one (student_type, base_slot).

    ``entries`` is a list of ``(BoolVar att, ComponentType, WeekPattern)``.
    A conflict exists when two overlapping-week-pattern entries are both 1.
    ``weight`` (= number_students) scales the penalty so each student in the
    type incurs the cost.

    Severity tiers:  lecture–lecture  >  lecture–workshop  >  workshop–workshop.
    """
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            att_i, type_i, wp_i = entries[i]
            att_j, type_j, wp_j = entries[j]

            if not patterns_overlap(wp_i, wp_j):
                continue

            both_lec = (type_i == ComponentType.LECTURE and type_j == ComponentType.LECTURE)
            any_lec  = (type_i == ComponentType.LECTURE or  type_j == ComponentType.LECTURE)
            if both_lec:
                sev = cfg.lecture_lecture_conflict_penalty
            elif any_lec:
                sev = cfg.lecture_workshop_conflict_penalty
            else:
                sev = cfg.workshop_workshop_conflict_penalty

            both = bool_and(model, att_i, att_j, f"cf[{sid},{base},{i},{j}]")
            penalties.append(sev * weight * both)