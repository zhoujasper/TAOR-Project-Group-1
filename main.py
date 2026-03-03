import time
import argparse
import threading
from pathlib import Path

from ortools.sat.python import cp_model

from data.loader import load_instance
from model.builder import build_model
from config.solver_config import apply_default_solver_config
from helpers import CpSatLogHelper, SolutionPrinter, spinner
from output_writer import write_all_outputs
from utils import make_output_dir


def main():
    t0 = time.time()

    # Input parsing
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=str, default=None)
    parser.add_argument("--no-debug", action="store_false", dest="debug")
    parser.add_argument("--no-validate", action="store_false", dest="validate")
    parser.add_argument("--no-soft", action="store_false", dest="soft")
    args = parser.parse_args()

    if not args.instance:
        instance_dir = Path("data/instances/demo_baseline")
    else:
        instance_dir = Path("data/instances") / args.instance
    dataset_name = instance_dir.name

    print("=" * 80)
    print(f"Loading instance from: {instance_dir}")
    print("=" * 80)


    # Load instance and print summary
    try:
        inst = load_instance(instance_dir, validate=args.validate)
        print(f"[STATUS] Instance loaded")
        print(f"         TimeslotKeys : {len(inst.timeslot_keys_list)}")
        print(f"         Courses   : {len(inst.courses)}  "
              f"(GW={len(inst.gateway_course_ids)}  "
              f"OPT={len(inst.optional_course_ids)}  "
              f"OUT={len(inst.outside_course_ids)})")
        total_stu = sum(s.number_students for s in inst.students)
        print(f"         Students  : {total_stu} total, {len(inst.students)} types (aggregated)")
    except Exception as e:
        print(f"[ERROR]  {e}")
        return
    
    t1 = time.time()
    print(f"[STATUS] Instance loaded in {t1 - t0:.1f}s")


    # Build model
    build_message = "[STATUS] Building model ..."
    stop_event_build = threading.Event()
    spin_thread_build = threading.Thread(
        target=spinner,
        args=(stop_event_build, build_message),
        daemon=True
    )
    spin_thread_build.start()

    try:
        model, vs = build_model(inst, soft=args.soft)
    except Exception as e:
        stop_event_build.set()
        spin_thread_build.join()
        print(f"\n[ERROR]  {e}")
        return
    finally:
        stop_event_build.set()
        spin_thread_build.join()

    t2 = time.time()
    print(f"[STATUS] Model built in {t2 - t1:.1f}s")


    # Solve model and save logs
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    log_helper = CpSatLogHelper()

    solve_message = "[STATUS] Solving model ..."
    stop_event_solve = threading.Event()
    spin_thread_solve = threading.Thread(
        target=spinner,
        args=(stop_event_solve, solve_message),
        daemon=True
    )
    spin_thread_solve.start()

    try:
        solver = cp_model.CpSolver()
        apply_default_solver_config(solver, debug=args.debug)
        callback = SolutionPrinter(stop_event_solve)
        status = log_helper.solve_and_log(model, solver, callback)
        elapsed = time.time() - t2
    except Exception as e:
        print(f"\n[ERROR]  Solver: {e}")
        return
    finally:
        stop_event_solve.set()
        spin_thread_solve.join()


    # Print status and write outputs
    print("=" * 80)
    status_str = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
    }.get(status, f"UNKNOWN({status})")

    print(f"Status : {status_str}   Time taken : {elapsed:.1f}s     Total time taken: {time.time() - t0:.1f}s")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        od = make_output_dir(dataset_name)
        write_all_outputs(inst, vs, solver, od)
        print(f"[STATUS] Finished\n")
        print(f"Raw log    : {log_helper.raw_path}")
        print(f"Core log   : {log_helper.core_path}")
        print(f"Outputs    : {od}")
    else:
        print("[ERROR]  No feasible solution")
        proto = model.Proto()
        print(f"         Variables   : {len(proto.variables)}")
        print(f"         Constraints : {len(proto.constraints)}")
        print(f"         Logs: {log_helper.raw_path}, {log_helper.core_path}")


if __name__ == "__main__":
    main()