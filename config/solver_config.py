import os
import random
import psutil
from ortools.sat.python import cp_model

def apply_default_solver_config(solver: cp_model.CpSolver, debug=True):
    if debug:
        p = solver.parameters
        p.max_time_in_seconds = 60 * 30  # 30 min
        p.num_search_workers = 4
        p.random_seed = 42
        p.log_search_progress = True
        p.log_to_stdout = False
        p.cp_model_presolve = True
        p.linearization_level = 1
        p.cp_model_probing_level = 2
        p.symmetry_level = 3
        print("\n[WARNING] DEBUG MODE ENABLED")
    else:
        p = solver.parameters
        p.max_time_in_seconds = 60 * 60 * 1   # 1 h
        p.num_search_workers = min(os.cpu_count(), 24)
        p.max_memory_in_mb = int(psutil.virtual_memory().total / (1024 * 1024) * 0.9)
        p.cp_model_presolve = True
        p.linearization_level = 2
        p.cp_model_probing_level = 2
        p.symmetry_level = 3
        p.cut_level = 2
        p.max_num_cuts = 20000
        p.use_sat_inprocessing = True
        p.log_search_progress = True
        p.log_to_stdout = False
        p.random_seed = random.randint(1, 1000000)
        print(f"\n[INFO]   WORKERS: {p.num_search_workers} | MEMORY: {p.max_memory_in_mb / 1024:.2f}GB | SEED: {p.random_seed}")