from ortools.sat.python import cp_model

from model.variables import build_variables
from model.constraints_courses import add_courses_constraints
from model.constraints_students import add_student_constraints
from model.objective import add_objective


def build_model(inst, soft = True):
    '''
    Create a CP-SAT model with variables, constraints, and objective.
    '''
    
    model = cp_model.CpModel()
    
    vs = build_variables(model, inst)
    
    if soft:
        add_courses_constraints(model, inst, vs)
        add_student_constraints(model, inst, vs)
        add_objective(model, inst, vs)
    # TODO: add hard constraints regardless of "soft" flag.

    return model, vs
