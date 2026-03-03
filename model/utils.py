from data.schema import ComponentType, WeekPattern
from ortools.sat.python import cp_model


def patterns_overlap(a, b):
    """Return True when two week-patterns can share the same physical slot."""
    if a == WeekPattern.ALL or b == WeekPattern.ALL:
        return True
    return a == b


def is_sectioned(comp):
    """A component is sectioned when students must be assigned to parallel sections."""
    return comp.component_type == ComponentType.WORKSHOP or comp.sections_max > 1


def sum_vars(vs):
    """Sum a list of variables / ints."""
    vs = list(vs)
    return sum(vs) if vs else 0


def bool_and(model: cp_model.CpModel, a, b, name):
    """Create z = a AND b (all BoolVar) using native boolean operations."""
    z = model.new_bool_var(name)
    model.add_implication(z, a)                   # z => a
    model.add_implication(z, b)                   # z => b
    model.add_bool_or([a.Not(), b.Not(), z])      # a ∧ b => z
    return z

def link_or(model: cp_model.CpModel, cond_list, target):
    """Link target <-> OR(cond_list)."""
    if not cond_list:
        model.add(target == 0)
    elif len(cond_list) == 1:
        model.add(target == cond_list[0])
    else:
        model.add_bool_or(cond_list).OnlyEnforceIf(target)
        model.add_bool_and([x.Not() for x in cond_list]).OnlyEnforceIf(target.Not())
