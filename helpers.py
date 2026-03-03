import re
import sys
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
from ortools.sat.python import cp_model

@dataclass
class CoreMetrics:
    solver_version: Optional[str] = None
    initial_vars_total: Optional[int] = None
    initial_bools: Optional[int] = None
    initial_ints: Optional[int] = None
    initial_primary_vars: Optional[int] = None
    initial_constraints_by_type: Optional[dict] = None
    presolved_vars_total: Optional[int] = None
    presolve_start_s: Optional[float] = None
    objective_sense: Optional[str] = None
    primal_objective: Optional[float] = None
    dual_bound: Optional[float] = None
    gap_ratio: Optional[float] = None
    gap_percent: Optional[float] = None
    status: Optional[str] = None
    conflicts: Optional[int] = None
    branches: Optional[int] = None
    propagations: Optional[int] = None
    integer_propagations: Optional[int] = None
    restarts: Optional[int] = None
    lp_iterations: Optional[int] = None
    wall_time_s: Optional[float] = None
    user_time_s: Optional[float] = None
    deterministic_time: Optional[float] = None
    gap_integral: Optional[float] = None
    solution_fingerprint: Optional[str] = None
    absolute_gap: Optional[float] = None


class CpSatLogHelper:
    def __init__(self, raw_path="", core_path=""):
        now = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        if raw_path == "":
            raw_path = f"log/cpsat_raw_log_{now}.txt"
        if core_path == "":
            core_path = f"log/cpsat_core_log_{now}.txt"
        self.raw_path = raw_path
        self.core_path = core_path

    def solve_and_log(self, model: cp_model.CpModel, solver: cp_model.CpSolver, callback=None):
        try:
            solver.parameters.log_search_progress = True
        except Exception:
            pass

        log_file = open(self.raw_path, "w", encoding="utf-8")

        def log_cb(msg):
            try:
                log_file.write(msg + "\n")
                log_file.flush()
            except Exception:
                pass

        solver.log_callback = log_cb

        t0 = time.time()
        status = solver.Solve(model, callback) if callback else solver.Solve(model)
        t1 = time.time()

        log_file.close()

        metrics = self.parse_raw_log(self.raw_path)
        if metrics.wall_time_s is None:
            metrics.wall_time_s = round(t1 - t0, 6)
        if metrics.primal_objective is not None and metrics.dual_bound is not None:
            if metrics.objective_sense == "max":
                metrics.absolute_gap = metrics.dual_bound - metrics.primal_objective
            else:
                metrics.absolute_gap = metrics.primal_objective - metrics.dual_bound
        self.write_core_report(metrics, self.core_path)
        return status

    def parse_raw_log(self, raw_path):
        with open(raw_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        m = CoreMetrics()

        ver = re.search(r"Starting CP-SAT solver v([0-9]+\.[0-9]+\.[0-9]+)", text)
        if ver:
            m.solver_version = ver.group(1)

        ps = re.search(r"Starting presolve at\s+([0-9]+(\.[0-9]+)?)s", text, re.IGNORECASE)
        if ps:
            m.presolve_start_s = float(ps.group(1))

        if "best:-inf" in text:
            m.objective_sense = "max"
        elif "best:inf" in text:
            m.objective_sense = "min"

        init_block = re.search(
            r"Initial optimization model.*?\n(#Variables:.*?)(?:\n\n|\r\n\r\n|Starting presolve|$)",
            text, re.IGNORECASE | re.DOTALL)
        if init_block:
            blk = init_block.group(1)
            v = re.search(r"#Variables:\s*([\d']+)", blk)
            if v:
                m.initial_vars_total = int(v.group(1).replace("'", ""))
            bb = re.search(r"#Variables:\s*[\d']+\s*\(#bools:\s*([\d']+)\s*#ints:\s*([\d']+)", blk)
            if bb:
                m.initial_bools = int(bb.group(1).replace("'", ""))
                m.initial_ints = int(bb.group(2).replace("'", ""))
            pv = re.search(r"\(([\d']+)\s+primary variables\)", blk)
            if pv:
                m.initial_primary_vars = int(pv.group(1).replace("'", ""))

        constraints = {}
        for name, count in re.findall(r"#(k[A-Za-z0-9_]+):\s*([\d']+)", text):
            if name.startswith("k"):
                constraints[name] = constraints.get(name, 0) + int(count.replace("'", ""))
        m.initial_constraints_by_type = constraints or None

        pres = re.search(r"Presolved optimization model.*?\n#Variables:\s*([\d']+)", text, re.IGNORECASE | re.DOTALL)
        if pres:
            m.presolved_vars_total = int(pres.group(1).replace("'", ""))

        summary_blocks = list(re.finditer(r"CpSolverResponse summary:\s*(.+?)(\n\s*\n|$)", text, re.IGNORECASE | re.DOTALL))
        if summary_blocks:
            block = summary_blocks[-1].group(1)

            def grab_float(pat):
                mm = re.search(pat, block, re.IGNORECASE)
                return float(mm.group(1)) if mm else None

            def grab_int(pat):
                mm = re.search(pat, block, re.IGNORECASE)
                return int(mm.group(1)) if mm else None

            def grab_str(pat):
                mm = re.search(pat, block, re.IGNORECASE)
                return mm.group(1) if mm else None

            st = grab_str(r"status:\s*([A-Z_]+)")
            if st:
                m.status = st.upper()
            obj = grab_float(r"objective:\s*(-?\d+(\.\d+)?([eE][-+]?\d+)?)")
            if obj is not None:
                m.primal_objective = obj
            bnd = grab_float(r"best_bound:\s*(-?\d+(\.\d+)?([eE][-+]?\d+)?)")
            if bnd is not None:
                m.dual_bound = bnd
            m.conflicts = grab_int(r"conflicts:\s*(\d+)")
            m.branches = grab_int(r"branches:\s*(\d+)")
            m.propagations = grab_int(r"propagations:\s*(\d+)")
            m.integer_propagations = grab_int(r"integer_propagations:\s*(\d+)")
            m.restarts = grab_int(r"restarts:\s*(\d+)")
            m.lp_iterations = grab_int(r"lp_iterations:\s*(\d+)")
            m.wall_time_s = grab_float(r"walltime:\s*([0-9]+(\.[0-9]+)?)")
            m.user_time_s = grab_float(r"usertime:\s*([0-9]+(\.[0-9]+)?)")
            m.deterministic_time = grab_float(r"deterministic_time:\s*([0-9]+(\.[0-9]+)?([eE][-+]?\d+)?)")
            m.gap_integral = grab_float(r"gap_integral:\s*([0-9]+(\.[0-9]+)?)")
            m.solution_fingerprint = grab_str(r"solution_fingerprint:\s*(0x[0-9a-fA-F]+)")

        if m.primal_objective is not None and m.dual_bound is not None:
            denom = max(1.0, abs(m.primal_objective))
            if m.objective_sense == "max":
                gap = (m.dual_bound - m.primal_objective) / denom
            else:
                gap = (m.primal_objective - m.dual_bound) / denom
            if abs(gap) < 1e-12:
                gap = 0.0
            m.gap_ratio = gap
            m.gap_percent = 100.0 * gap
        return m

    def write_core_report(self, metrics, core_path):
        with open(core_path, "w", encoding="utf-8") as f:
            f.write("[HEADER]\n")
            f.write(f"solver_version: {metrics.solver_version or '(not parsed)'}\n\n")
            f.write("[MODEL_SIZE_INITIAL]\n")
            f.write(f"initial_vars_total: {metrics.initial_vars_total if metrics.initial_vars_total is not None else '(not parsed)'}\n")
            f.write(f"initial_bools: {metrics.initial_bools if metrics.initial_bools is not None else '(not parsed)'}\n")
            f.write(f"initial_ints: {metrics.initial_ints if metrics.initial_ints is not None else '(not parsed)'}\n")
            f.write(f"initial_primary_vars: {metrics.initial_primary_vars if metrics.initial_primary_vars is not None else '(not parsed)'}\n")
            if metrics.initial_constraints_by_type:
                for k in sorted(metrics.initial_constraints_by_type.keys()):
                    f.write(f"{k}: {metrics.initial_constraints_by_type[k]}\n")
            else:
                f.write("constraints_by_type: (not parsed)\n")
            f.write("\n[PRESOLVE]\n")
            f.write(f"presolve_start_s: {metrics.presolve_start_s if metrics.presolve_start_s is not None else '(not parsed)'}\n")
            f.write(f"presolved_vars_total: {metrics.presolved_vars_total if metrics.presolved_vars_total is not None else '(not parsed)'}\n")
            if metrics.initial_vars_total is not None and metrics.presolved_vars_total is not None:
                f.write(f"variables: {metrics.initial_vars_total} -> {metrics.presolved_vars_total} (reduced {metrics.initial_vars_total - metrics.presolved_vars_total})\n")
            f.write("\n[BOUNDS_AND_GAP]\n")
            f.write(f"objective_sense: {metrics.objective_sense or '(unknown)'}\n")
            f.write(f"primal_objective: {metrics.primal_objective if metrics.primal_objective is not None else '(not parsed)'}\n")
            f.write(f"dual_bound: {metrics.dual_bound if metrics.dual_bound is not None else '(not parsed)'}\n")
            f.write(f"absolute_gap: {metrics.absolute_gap if metrics.absolute_gap is not None else '(not computed)'}\n")
            f.write(f"gap_ratio: {metrics.gap_ratio if metrics.gap_ratio is not None else '(not computed)'}\n")
            f.write(f"gap_percent: {metrics.gap_percent if metrics.gap_percent is not None else '(not computed)'}\n")
            f.write("\n[SEARCH_STATS_FINAL]\n")
            f.write(f"conflicts: {metrics.conflicts if metrics.conflicts is not None else '(not parsed)'}\n")
            f.write(f"branches: {metrics.branches if metrics.branches is not None else '(not parsed)'}\n")
            f.write(f"propagations: {metrics.propagations if metrics.propagations is not None else '(not parsed)'}\n")
            f.write(f"integer_propagations: {metrics.integer_propagations if metrics.integer_propagations is not None else '(not parsed)'}\n")
            f.write(f"restarts: {metrics.restarts if metrics.restarts is not None else '(not parsed)'}\n")
            f.write(f"lp_iterations: {metrics.lp_iterations if metrics.lp_iterations is not None else '(not parsed)'}\n")
            f.write(f"wall_time_s: {metrics.wall_time_s if metrics.wall_time_s is not None else '(not parsed)'}\n")
            f.write(f"user_time_s: {metrics.user_time_s if metrics.user_time_s is not None else '(not parsed)'}\n")
            f.write(f"deterministic_time: {metrics.deterministic_time if metrics.deterministic_time is not None else '(not parsed)'}\n")
            f.write(f"gap_integral: {metrics.gap_integral if metrics.gap_integral is not None else '(not parsed)'}\n")
            f.write(f"solution_fingerprint: {metrics.solution_fingerprint if metrics.solution_fingerprint is not None else '(not parsed)'}\n")
            f.write("\n[TERMINATION]\n")
            f.write(f"status: {metrics.status or '(not parsed)'}\n")
            f.write("\n[RAW_METRICS_DICT]\n")
            f.write(str(asdict(metrics)) + "\n")


# Small tool to show a spinner while the model is being solved.
def spinner(stop_event, message):
    while not stop_event.is_set():
        for ch in "|/-\\":
            sys.stdout.write(f"\r{message} {ch}")
            sys.stdout.flush()
            time.sleep(0.1)
            if stop_event.is_set():
                break
    sys.stdout.write(f"\r{message} Done\n")
    sys.stdout.flush()


class SolutionPrinter(cp_model.CpSolverSolutionCallback):
    """Print intermediate solution summaries during solving."""
    def __init__(self, stop_spinner_event=None):
        super().__init__()
        self._count = 0
        self._start = time.time()
        self._stop_spinner = stop_spinner_event

    def on_solution_callback(self):
        if self._stop_spinner and not self._stop_spinner.is_set():
            self._stop_spinner.set()
            time.sleep(0.15)  # let spinner thread clear its line
        self._count += 1
        elapsed = time.time() - self._start
        obj = self.ObjectiveValue()
        bound = self.BestObjectiveBound()
        print(f"\r         Solution #{self._count}: obj={obj:.0f}  bound={bound:.0f}  time={elapsed:.1f}s")
