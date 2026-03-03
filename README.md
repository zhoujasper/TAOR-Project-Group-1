# TAOR Project – Mid-project Deliverable

This repository contains our baseline CP-SAT timetable optimisation pipeline for the TAOR group project.

## 1) What this deliverable includes

For Assignment 2 (mid-project), the deliverable is the **working baseline code pipeline**:

1. load and validate one instance,
2. build and solve the optimisation model,
3. write a full output pack for analysis.

The intended assessment scope for this deliverable is:

- instance: `data/instances/demo_baseline`
- objective weights from `config/objective_config.json`
- output CSV pack under `output/run_demo_baseline_<timestamp>/`

## 2) Current scope and limitation (mid-project)

This mid-project version focuses on baseline feasibility and conflict-aware scheduling.

- We currently expose **single-section baseline settings** in `demo_baseline`.
- In this instance, all components have `sections_max = 1`.
- Parallel workshop opening is treated as ongoing work for the next stage and is not part of the visible mid-project baseline results.

## 3) Environment and dependencies

- Python 3.11+ (tested in local virtual environment)
- Packages in `requirements.txt`:
  - `ortools>=9.15,<10.0`
  - `psutil>=5.9,<7.0`

Install:

```bash
pip install -r requirements.txt
```

## 4) How to run

Run baseline instance:

```bash
python main.py --instance demo_baseline
```

Optional flags:

- `--no-validate`: skip input validation (faster on trusted inputs)
- `--no-soft`: disable soft-conflict objective terms
- `--no-debug`: disable detailed solver debug run (for server only, not recommended for local runs)

If `--instance` is not provided, the default is also `data/instances/demo_baseline`.

## 5) Expected outputs

Each successful run creates a new folder in `output/` and writes:

- `timetable.csv`
- `student_courses.csv`
- `enrollment.csv`
- `student_assignments.csv`
- `conflicts.csv`
- `conflict_summary.csv`
- `solution_summary.csv`

Solver logs are saved in `log/`.

## 6) Main project structure

- `main.py`: entry point (load → build → solve → write outputs)
- `data/`: schema, loaders, validation, and instances
- `model/`: decision variables, constraints, objective, model builder
- `config/`: solver and objective configuration
- `output_writer.py`: CSV extraction and export
- `output/`: generated run outputs
- `log/`: raw/core CP-SAT logs

## 7) Notes for marker/reviewer

- This repository may contain additional experimental instance folders under `data/instances/`.
- For Assignment 2 marking, please evaluate the baseline deliverable using `demo_baseline` only.
- The mid-project report describes ongoing enhancement work (including richer parallel workshop modelling) planned for the final stage.

## 8) File-by-file explanation (detailed)

This section explains the purpose of each important file in this repository.

### Root files

- `README.md`: project overview, reproducibility instructions, and file reference for markers.
- `main.py`: main entry point; parses arguments, loads instance, builds model, solves, and writes outputs.
- `helpers.py`: solver log helper, spinner/progress display, and solution callback utilities.
- `output_writer.py`: extracts solver values and writes all output CSV files.
- `utils.py`: shared utilities such as output-directory creation and generic helpers.
- `requirements.txt`: Python dependency list.
- `constraints and objective.md`: full mathematical formulation and modelling notes (long-form technical documentation).
- `.gitignore`: Git ignore rules for environments, caches, logs, and generated artifacts.

### `config/`

- `config/__init__.py`: package marker for configuration modules.
- `config/objective_config.json`: objective weights (activation penalty, clash penalties, desire bonus).
- `config/objective_config.py`: loader/parser for objective settings and defaults.
- `config/solver_config.py`: default CP-SAT solver parameter setup (workers, logging, limits, etc.).

### `data/`

- `data/__init__.py`: package marker for data modules.
- `data/loader.py`: reads CSV/JSON instance files and builds in-memory objects.
- `data/schema.py`: core data classes and validation rules for instance consistency.
- `data/utils.py`: utility helpers for reading/writing data and common parsing logic.

### `data/instances/` (input instances)

#### Baseline instance used for Assignment 2

- `data/instances/demo_baseline/courses.csv`: course-level metadata (course id, kind, credits, caps, restrictions).
- `data/instances/demo_baseline/components.csv`: component-level definitions (lecture/workshop structure, section bounds, capacity, allowed slots).
- `data/instances/demo_baseline/students.csv`: student-type/cohort input (programme, size, compulsory and desired courses).
- `data/instances/demo_baseline/rules.json`: degree and scheduling rules by programme (credits, gateway/optional bounds, global limits).
- `data/instances/demo_baseline/timeslot_config.json`: calendar/time-grid config (years, semesters, day/period ranges, week patterns).

#### Experimental folders (not the marking target for Assignment 2)

- `data/instances/odd_temp/demo_config_1/*`: temporary stress-test instance variant with incompatibility file.
- `data/instances/odd_temp/demo_config_1_no_student/*`: variant for structure testing under altered student settings.
- `data/instances/odd_temp/demo_config_2_extreme_8outside/*`: extreme outside-commitment test variant.
- `data/instances/odd_temp/demo_config_2_no_student_extreme/`: reserved temp folder (currently empty).
- `data/instances/odd_temp/demo_config_3_10_credit/*`: low-credit-pattern test variant.
- `data/instances/odd_temp/demo_config_3_no_student/*`: structural no-student variant.
- `data/instances/odd_temp/demo_config_4_capacity/*`: capacity-stress test variant.

### `model/`

- `model/__init__.py`: package marker for model modules.
- `model/builder.py`: orchestrates model assembly by creating variables, constraints, and objective.
- `model/variables.py`: creates CP-SAT decision variables (`take`, `open`, `assign`, `active`).
- `model/constraints_students.py`: student-level constraints (credits, course counts, compulsory rules, clash structure).
- `model/constraints_courses.py`: course-level constraints (activation, section bounds, capacities, offering logic).
- `model/objective.py`: objective construction (weighted clashes, activation penalties, desire terms).
- `model/utils.py`: model helper functions (logical linking, overlap checks, common expressions).

### Runtime-generated folders/files

- `log/cpsat_raw_log_<timestamp>.txt`: raw solver log stream for debug/performance inspection.
- `log/cpsat_core_log_<timestamp>.txt`: filtered core solver summary log.
- `output/run_demo_baseline_<timestamp>/timetable.csv`: opened timetable events by course/component/timeslot.
- `output/run_demo_baseline_<timestamp>/student_courses.csv`: course selections by student type.
- `output/run_demo_baseline_<timestamp>/enrollment.csv`: enrollment counts and programme breakdown per course.
- `output/run_demo_baseline_<timestamp>/student_assignments.csv`: student-type assignment to section/timeslot.
- `output/run_demo_baseline_<timestamp>/conflicts.csv`: detailed pairwise clashes and severity labels.
- `output/run_demo_baseline_<timestamp>/conflict_summary.csv`: programme-level and overall conflict statistics.
- `output/run_demo_baseline_<timestamp>/solution_summary.csv`: high-level run summary (status/objective/key counts).