# Complete Formulation: Constraints and Objective

## What This Document Is About

This document describes the **mathematical model** behind a university course-timetabling optimiser. The system decides:

1. **Which courses to offer** and in which semester / timeslot.
2. **Which courses each student should take**, respecting degree requirements (credits, course counts, compulsory courses, etc.).
3. **How to assign students to workshop sections** when a course has multiple sections.
4. **How to minimise timetable clashes** while fulfilling as many student preferences as possible.

The model is solved with [Google OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver), a constraint-programming solver that works with binary (0/1) decision variables.

> **Key modelling choice — student aggregation**: Students who share the same degree programme, year group, compulsory courses, and desired courses are grouped into a single *student type* and given an identical schedule. This dramatically reduces the number of variables. The trade-off is that enrollment counts become "quantised" (rounded to the nearest group size); see §8.4 for a full discussion. The maximum group size $G$ is configurable via `max_group_size` in `rules.json`.

### Precision Summary at a Glance

| Category                       | Constraints          | Precision                                                                                          |
| ------------------------------ | -------------------- | -------------------------------------------------------------------------------------------------- |
| Per-type schedule rules        | S1–S15, S17         | **Exact** — every student in the type satisfies the rule.                                         |
| Weighted enrollment / capacity | S16, C6, C8, C9      | **Granular** — exact in the model, but aggregation quantises enrollment in blocks of at most $G$. |
| Symmetry breaking              | S18                  | **Slightly over-strict** when subgroup sizes differ by 1; negligible in practice.                  |
| Course structure               | C1–C5, C7, C10, C11 | **Exact**.                                                                                         |
| Objective terms                | O1–O3               | O2 exact; O1 and O3 granular (≤$G$).                                                              |

---

# Part I — English Version

## 1. Sets and Indices

The following sets define the "universe" of the model — what students, courses, time slots, etc. exist.

| Symbol                                               | Description                                                                                                                                   |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| $\mathcal{S}$                                        | Set of student types (post-aggregation). Each type groups students sharing the same programme, year, compulsory courses, and desired courses. |
| $\mathcal{C}$                                        | Set of all courses; partitioned into$\mathcal{C}^{GW}$ (gateway), $\mathcal{C}^{OPT}$ (optional), $\mathcal{C}^{OUT}$ (outside).              |
| $\mathcal{P}_c$                                      | Set of components for course$c$ (lectures, workshops).                                                                                        |
| $\mathcal{P}_c^{\text{sec}} \subseteq \mathcal{P}_c$ | Sectioned components of$c$ (workshop-type or `sections_max > 1`).                                                                             |
| $\mathcal{K}$                                        | Set of timeslot keys. Each$k \in \mathcal{K}$ is a tuple $(y_k, \sigma_k, w_k, d_k, \pi_k)$: year, semester, week-pattern, day, period.       |
| $\mathcal{K}_{c,p}$                                  | Allowed timeslot keys for component$p$ of course $c$ (filtered by allowed days/periods/years/semesters/forbidden keys).                       |
| $\mathcal{Y}_s$                                      | Set of years in student type$s$'s planning horizon.                                                                                           |
| $\Sigma_s$                                           | Set of semesters for student type$s$.                                                                                                         |
| $\mathcal{Y}, \Sigma$                                | Global sets of years / semesters from timeslot keys.                                                                                          |
| $\mathcal{D}$                                        | Set of weekdays.                                                                                                                              |
| $\Pi$                                                | Set of periods.                                                                                                                               |
| $\mathcal{W} = \{A, O, E\}$                          | Week patterns: ALL, ODD, EVEN.                                                                                                                |
| $\text{base}(k)$                                     | The base slot of key$k$, collapsing week-pattern: $(y_k, \sigma_k, d_k, \pi_k)$.                                                              |

## 2. Parameters

These are the **input data** — numbers read from CSV/JSON files that the solver treats as fixed constants. They describe degree rules, course properties, and capacity limits.

| Symbol                                                   | Description                                                                                                                          | Source                                                |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------- |
| $N_s$                                                    | Number of students in type$s$                                                                                                        | `Student.number_students`                             |
| $\text{cr}_c$                                            | Credits for course$c$                                                                                                                | `Course.credits`                                      |
| $\text{prog}_s$                                          | Programme of student type$s$ (SINGLE, JOINT\_*)                                                                                      | `Student.programme`                                   |
| $\text{comp}_s$                                          | Compulsory course IDs for type$s$                                                                                                    | `Student.compulsory_course_ids`                       |
| $\text{des}_s$                                           | Desired course IDs for type$s$                                                                                                       | `Student.desired_course_ids`                          |
| $R_s$                                                    | Rule set for type$s$ (per-programme)                                                                                                 | `DegreeRules.for_student(s)`                          |
| $R_s^{\text{gw\_min\_sem}}, R_s^{\text{gw\_max\_sem}}$   | Gateway bounds per semester                                                                                                          | `StudentRules`                                        |
| $R_s^{\text{opt\_min\_sem}}, R_s^{\text{opt\_max\_sem}}$ | Optional bounds per semester                                                                                                         | `StudentRules`                                        |
| $R_s^{\text{crs\_min\_sem}}, R_s^{\text{crs\_max\_sem}}$ | Course count bounds per semester                                                                                                     | `StudentRules`                                        |
| $R_s^{\text{cr\_min\_sem}}, R_s^{\text{cr\_max\_sem}}$   | Credit bounds per semester                                                                                                           | `StudentRules`                                        |
| $R_s^{\text{cr\_year}}$                                  | Total credits per year (equality)                                                                                                    | `StudentRules.total_credits_per_year`                 |
| $R_s^{\text{out\_cr\_year}}$                             | Outside credits required per year                                                                                                    | `StudentRules.outside_credits_required_per_year`      |
| $R_s^{\text{gw\_min\_yr}}, R_s^{\text{gw\_max\_yr}}$     | Gateway bounds per year                                                                                                              | `StudentRules`                                        |
| $R_s^{\text{opt\_min\_yr}}, R_s^{\text{opt\_max\_yr}}$   | Optional bounds per year                                                                                                             | `StudentRules`                                        |
| $R_s^{\text{crs\_min\_yr}}, R_s^{\text{crs\_max\_yr}}$   | Course count bounds per year                                                                                                         | `StudentRules`                                        |
| $R_s^{\text{gw\_total}}$                                 | Total gateway courses required (across all years)                                                                                    | `StudentRules.gateway_total_required`                 |
| $R_s^{\text{balanced}}$                                  | Whether to enforce balanced credits across semesters                                                                                 | `StudentRules.balanced_credits`                       |
| $G_\sigma^{GW}, G_\sigma^{OPT}$                          | Global gateway / optional offering count per semester                                                                                | `DegreeRules.global_*_per_semester`                   |
| $G$                                                      | Maximum students per aggregated subgroup; groups larger than$G$ are split into $\lceil N / G \rceil$ subgroups of roughly equal size | `DegreeRules.max_group_size` (default 999 = no split) |
| $\text{gap}_{\max}$                                      | Student max daily consecutive gap                                                                                                    | `DegreeRules.student_max_daily_gap`                   |
| $\text{day}_{\max}$                                      | Course max slots per day                                                                                                             | `DegreeRules.course_max_slots_per_day`                |
| $\overline{E}_c, \underline{E}_c$                        | Course enrollment cap (max / min)                                                                                                    | `Course.cap_max, cap_min`                             |
| $n_p^w$                                                  | Number of meetings per week for component$p$                                                                                         | `CourseComponent.number_per_week`                     |
| $\underline{S}_p, \overline{S}_p$                        | Section count bounds (min / max)                                                                                                     | `CourseComponent.sections_min/max`                    |
| $\underline{Q}_p, \overline{Q}_p$                        | Section capacity bounds (min / max)                                                                                                  | `CourseComponent.section_cap_min/max`                 |

**Notation convention**: All sums below are taken only over indices for which the corresponding variable was created. Domain restrictions imposed during variable creation (banned courses, allowed years/semesters, programme restrictions) are implicitly applied.

## 3. Decision Variables

These are the **unknowns** the solver must determine. Every variable is binary (0 or 1), representing a yes/no decision. Within a student type, all students share the same schedule, so one set of variables covers the entire group.

All variables are **binary** (BoolVar). Within an aggregated type, all $N_s$ students share an identical schedule.

| Variable              | Domain    | Meaning                                                                                 |
| --------------------- | --------- | --------------------------------------------------------------------------------------- |
| $t_{s,c,y,\sigma}$    | $\{0,1\}$ | Type$s$ takes course $c$ in year $y$, semester $\sigma$                                 |
| $o_{c,p,k}$           | $\{0,1\}$ | Component$p$ of course $c$ is open at timeslot key $k$                                  |
| $a_{s,c,p,k}$         | $\{0,1\}$ | Type$s$ is assigned to section $(c, p, k)$; only for $p \in \mathcal{P}_c^{\text{sec}}$ |
| $\alpha_{c,y,\sigma}$ | $\{0,1\}$ | Course$c$ is offered (active) in year $y$, semester $\sigma$                            |

```python
# variables.py — all BoolVar
take_vars[(s.id, c.id, y, sem)] = model.new_bool_var(...)
open_vars[(c.id, comp.id, k.id)] = model.new_bool_var(...)
assign_vars[(s.id, c.id, comp.id, k.id)] = model.new_bool_var(...)   # sectioned only
active_vars[(c.id, y, sem)] = model.new_bool_var(...)
```

## 4. Auxiliary Variables

These variables are **not direct decisions** — they are intermediate helpers created automatically by specific constraints or the objective function. They let us express complex logical conditions ("if A and B then C") within the linear framework.

Created inline by constraints / objective:

| Variable                               | Domain         | Meaning                                                                                                              | Created in                      |
| -------------------------------------- | -------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| $\beta_{c,\sigma}$                     | $\{0,1\}$      | Course$c$ offered in semester $\sigma$ (any year)                                                                    | `constraints_courses.py` (C1)   |
| $h_{s,y}$                              | $\{0,1\}$      | Type$s$ takes ≥ 1 optional in year $y$                                                                              | `constraints_students.py` (S8)  |
| $\text{att}_{s,y,\sigma,\omega,d,\pi}$ | $\{0,1\}$      | Type$s$ has any activity at $(d, \pi)$ on physical week $\omega$                                                     | `constraints_students.py` (S17) |
| $\text{parent}(s)$                     | string or None | If$s$ was split from a larger type, the original type id shared by all sibling subgroups. `None` means no splitting. | `Student.parent_type`           |
| $z^{\text{att}}_{s,c,p,k}$             | $\{0,1\}$      | Attendance:$t_{s,c,y,\sigma} \wedge o_{c,p,k}$ (non-sectioned)                                                       | `objective.py` (O3)             |
| $z^{\text{cf}}_{s,b,i,j}$              | $\{0,1\}$      | Both activities$i,j$ overlap at base $b$                                                                             | `objective.py` (O3)             |
| $\delta_{c,y,\sigma,\omega,d,\pi}$     | $\{0,1\}$      | Course$c$ uses period $\pi$ on day $d$ (physical week $\omega$)                                                      | `constraints_courses.py` (C11)  |

## 5. Student-Level Constraints

These constraints ensure every student type gets a valid, rule-compliant schedule. They cover degree requirements (how many courses, how many credits), compulsory course enrollment, timetable quality (daily gaps), and symmetry breaking for subgroups.

> Source: `model/constraints_students.py`

---

### S1. Per-Semester Gateway Count

> Each semester, each student must take a number of (Mathematics) gateway courses within the required range.

$$
R_s^{\text{gw\_min\_sem}} \;\leq\; \sum_{\substack{c \in \mathcal{C}^{GW}}} t_{s,c,y,\sigma} \;\leq\; R_s^{\text{gw\_max\_sem}}
$$

for each $s \in \mathcal{S},\; y \in \mathcal{Y}_s,\; \sigma \in \Sigma_s$.
The upper/lower bounds are enforced independently only when they are non-trivial ($R_s^{\text{gw\_min\_sem}} > 0$ and $R_s^{\text{gw\_max\_sem}} < 999$); and this constriant will be skipped when the student doesn't have any gateway course choices in that semester.

```python
if sem_gw:
    if rule.gateway_min_per_semester > 0:
        model.add(sum(sem_gw) >= rule.gateway_min_per_semester)
    if rule.gateway_max_per_semester < 999:
        model.add(sum(sem_gw) <= rule.gateway_max_per_semester)
```

---

### S2. Per-Semester Optional Count

> Each semester, each student must take a number of (Mathematics) optional courses within the required range.

$$
R_s^{\text{opt\_min\_sem}} \;\leq\; \sum_{\substack{c \in \mathcal{C}^{OPT}}} t_{s,c,y,\sigma} \;\leq\; R_s^{\text{opt\_max\_sem}}
$$

for each $s, y, \sigma$. Same guard conditions as stated in S1.

```python
if sem_opt:
    if rule.optional_min_per_semester > 0:
        model.add(sum(sem_opt) >= rule.optional_min_per_semester)
    if rule.optional_max_per_semester < 999:
        model.add(sum(sem_opt) <= rule.optional_max_per_semester)
```

---

### S3. Per-Semester Course Count

> Each semester, each student must take a total number of courses (gateway + optional + outside) within the allowed range.

$$
R_s^{\text{crs\_min\_sem}} \;\leq\; \sum_{c} t_{s,c,y,\sigma} \;\leq\; R_s^{\text{crs\_max\_sem}}
$$

for each $s, y, \sigma$. Same guard conditions as stated in S1.

```python
if sem_all:
    if rule.courses_min_per_semester > 0:
        model.add(sum(sem_all) >= rule.courses_min_per_semester)
    if rule.courses_max_per_semester < 999:
        model.add(sum(sem_all) <= rule.courses_max_per_semester)
```

---

### S4. Per-Semester Credit Bounds

> Each semester, each student's total credit load must stay within the minimum and maximum range, preventing underloading or overloading.

$$
R_s^{\text{cr\_min\_sem}} \;\leq\; \sum_{c} \text{cr}_c \cdot t_{s,c,y,\sigma} \;\leq\; R_s^{\text{cr\_max\_sem}}
$$

for each $s, y, \sigma$. Same guard conditions as stated in S1.

```python
if sem_credits:
    sem_credit_expr = sum(sem_credits)  # each term = tv * c.credits
    if rule.credits_min_per_semester > 0:
        model.add(sem_credit_expr >= rule.credits_min_per_semester)
    if rule.credits_max_per_semester < 999:
        model.add(sem_credit_expr <= rule.credits_max_per_semester)
```

---

### S5. Total Credits Per Year (Equality)

> Each year, each student's total credits across both semesters must exactly equal the required annual credit load (e.g., 120 credits/year).

$$
\sum_{\sigma \in \Sigma_s} \sum_{c} \text{cr}_c \cdot t_{s,c,y,\sigma} \;=\; R_s^{\text{cr\_year}}
$$

for each $s, y$.

```python
if year_total:
    model.add(sum(year_total) == rule.total_credits_per_year)
```

---

### S6. Outside Credits Per Year

> Joint-programme students must take enough credit from *other* department each year (e.g., a Maths-CS joint student needs a certain number of CS credits).

$$
\sum_{\sigma} \sum_{c \in \mathcal{C}^{OUT}} \text{cr}_c \cdot t_{s,c,y,\sigma} \;\geq\; R_s^{\text{out\_cr\_year}}
$$

for each student $s$  on a joint-programme ($\text{prog}_s \neq \text{SINGLE}$), and each $y$. Same guard condition as stated in S1, but only the lower bound is enforced ($R_s^{\text{out\_cr\_year}} > 0$).

```python
if rule.outside_credits_required_per_year > 0 and year_outside:
    model.add(sum(year_outside) >= rule.outside_credits_required_per_year)
```

---

### S7. Per-Year Gateway Count

> Each year, each student must take a number of (Mathematics) gateway courses within the required range.

$$
R_s^{\text{gw\_min\_yr}} \;\leq\; \sum_{\sigma} \sum_{c \in \mathcal{C}^{GW}} t_{s,c,y,\sigma} \;\leq\; R_s^{\text{gw\_max\_yr}}
$$

for each $s, y$. Same guard conditions as stated in S1.

```python
if year_gw:
    model.add(sum(year_gw) >= rule.gateway_min_per_year)
    model.add(sum(year_gw) <= rule.gateway_max_per_year)
```

---

### S8. Per-Year Optional Count (Conditional Minimum)

> Each year, each student can either take no optional courses, or (if they take any) they must take a number of optional courses within the required range. This “all-or-nothing” rule uses a small Boolean switch to speed up solving.

Define $\text{opt}_y = \sum_{\sigma} \sum_{c \in \mathcal{C}^{OPT}} t_{s,c,y,\sigma}$.

**Upper bound** (unconditional):

$$
\text{opt}_y \;\leq\; R_s^{\text{opt\_max\_yr}}
$$

**Conditional minimum** (when $R_s^{\text{opt\_min\_yr}} > 0$):

Introduce auxiliary $h_{s,y} \in \{0,1\}$ with:

$$
h_{s,y} = 1 \;\Leftrightarrow\; \text{opt}_y \geq 1
$$

$$
h_{s,y} = 1 \;\Rightarrow\; \text{opt}_y \geq R_s^{\text{opt\_min\_yr}}
$$

**Effective domain**: $\text{opt}_y \in \{0\} \cup [R_s^{\text{opt\_min\_yr}},\; R_s^{\text{opt\_max\_yr}}]$.

```python
if rule.optional_max_per_year < 999:
    model.add(opt_sum <= rule.optional_max_per_year)

if rule.optional_min_per_year > 0:
    has_opt = model.new_bool_var(f"has_opt[{s.id},Y{y}]")
    model.add(opt_sum >= 1).OnlyEnforceIf(has_opt)
    model.add(opt_sum == 0).OnlyEnforceIf(has_opt.Not())
    model.add(opt_sum >= rule.optional_min_per_year).OnlyEnforceIf(has_opt)
```

---

### S9. Per-Year Course Count

> Each year, each student must take a total number of courses (gateway + optional + outside) within the allowed range.

$$
R_s^{\text{crs\_min\_yr}} \;\leq\; \sum_{\sigma} \sum_{c} t_{s,c,y,\sigma} \;\leq\; R_s^{\text{crs\_max\_yr}}
$$

for each $s, y$.

```python
if year_all:
    if rule.courses_min_per_year > 0:
        model.add(sum(year_all) >= rule.courses_min_per_year)
    if rule.courses_max_per_year < 999:
        model.add(sum(year_all) <= rule.courses_max_per_year)
```

---

### S10. Balanced Credits Across Semesters

> If required by the programme rules, each student must take equal credits in semester 1 and semester 2 (e.g., 60 + 60 = 120) to prevent an unbalanced workload.

When $R_s^{\text{balanced}} = \text{true}$ and $|\Sigma_s| = 2$ (semesters $\sigma_1, \sigma_2$):

$$
\sum_c \text{cr}_c \cdot t_{s,c,y,\sigma_1} \;=\; \sum_c \text{cr}_c \cdot t_{s,c,y,\sigma_2}
$$

for each $s, y$.

```python
if rule.balanced_credits and len(s_sems) == 2:
    for y in s_years:
        s1_expr = sem_credit_sums.get((y, s_sems[0]))
        s2_expr = sem_credit_sums.get((y, s_sems[1]))
        if s1_expr is not None and s2_expr is not None:
            model.add(s1_expr == s2_expr)
```

---

### S11. Total Gateway Requirement (Across All Years)

> Across the final two years, each student must take at least the required total number of gateway courses.

$$
\sum_{y \in \mathcal{Y}_s} \sum_{\sigma} \sum_{c \in \mathcal{C}^{GW}} t_{s,c,y,\sigma} \;\geq\; R_s^{\text{gw\_total}}
$$

for each $s$.

```python
if all_gw_vars:
    model.add(sum(all_gw_vars) >= rule.gateway_total_required)
```

---

### S12. Compulsory Course Enrollment

> Across the final two years, each student must take **each** of their compulsory courses at least once.

$$
\sum_{y \in \mathcal{Y}_s} \sum_{\sigma \in \Sigma_s} t_{s,c,y,\sigma} \;\geq\; 1
$$

for each $s$ and each compulsory course $c \in \text{comp}_s$.

```python
for cid in s.compulsory_course_ids:
    takes = [take_by_sys.get((s.id, y, sem), {}).get(cid)
             for y in s_years for sem in s_sems]
    takes = [tv for tv in takes if tv is not None]
    if takes:
        model.add(sum(takes) >= 1)
```

---

### S13. Course Uniqueness

> Each student is not allowed to take same course twice (i.e., no repeats).

$$
\sum_{y,\sigma} t_{s,c,y,\sigma} \;\leq\; 1
$$

for each $s$ and each course $c$.

```python
for cid, tvs in course_takes.items():
    if len(tvs) > 1:
        model.add(sum(tvs) <= 1)
```

---

### S14. Sectioned Component Attendance

> If a student takes a course, the number of component sessions they are assigned to must equal the required weekly attendance for that component, $n_p^w$; if they do not take the course, they receive no component assignments. (e.g., if a course offers multiple parallel workshop sections, the student will be only assigned to one section.)

$$
\sum_{k:\; y_k=y,\, \sigma_k=\sigma} a_{s,c,p,k} \;=\; n_p^w \cdot t_{s,c,y,\sigma}
$$

If the type takes the course ($t=1$), exactly $n_p^w$ section-slots are assigned. If $t=0$, no assignments.

```python
for compid, comp in sectioned_by_course.get(cid, []):
    take_var = vs.take[(s.id, cid, y, sem)]
    assigns = assign_by_sct.get((s.id, cid, compid, y, sem), [])
    if assigns:
        model.add(sum(assigns) == comp.number_per_week * take_var)
    else:
        model.add(take_var == 0)
```

---

### S15. Take-Active Consistency

> If any student takes a course, that course must be offered (active). A course cannot have students without being officially open.

$$
t_{s,c,y,\sigma} = 1 \;\Rightarrow\; \alpha_{c,y,\sigma} = 1
$$

for each $(s, c, y, \sigma)$.

```python
for (sid, cid, y, sem), take_var in vs.take.items():
    act = vs.active[(cid, y, sem)]
    model.add_implication(take_var, act)
```

---

### S16. Course Enrollment Capacity

> If a course is offered, total enrolment must be within its capacity limits, counted using group size $N_s$.

$$
\alpha_{c,y,\sigma} = 1 \;\Rightarrow\; \underline{E}_c \;\leq\; \sum_{s} N_s \cdot t_{s,c,y,\sigma} \;\leq\; \overline{E}_c
$$

for each course $c$ with specified capacity range, and each semester $(y, \sigma)$.

```python
# take_by_cys stores N_s * t_{s,c,y,σ} terms
enrollments = take_by_cys.get((c.id, y, sem), [])
if c.cap_max < 999:
    model.add(s <= c.cap_max).OnlyEnforceIf(act)
if c.cap_min > 0:
    model.add(s >= c.cap_min).OnlyEnforceIf(act)
```

---

### S17. Max Daily Consecutive Gap

> If timetable compactness is considered, we can limit the maximum gap between two consecutive classes within a day. For example, with $\text{gap}_{\max} = 4$, a student cannot have a 9:00 class and then no further class until 15:00.

For each student type $s$, year $y$, semester $\sigma$, day $d$, week pattern $\omega \in \{\text{even}, \text{odd}\}$:

**Step 1**: For each period $\pi$, create attendance indicator $\text{att}_{s,y,\sigma,\omega,d,\pi} \in \{0,1\}$, which equals to 1 if the student has any scheduled activity in that period.

For non-sectioned component $p$:

$$
\text{att} \;\geq\; t_{s,c,y,\sigma} + o_{c,p,k} - 1
$$

For sectioned component $p$:

$$
\text{att} \;\geq\; a_{s,c,p,k}
$$

In the absence of any scheduled activity in that period, the solver will keep $att=0$, as setting $att=1$ would make the constraint below harder to satisfy.

**Step 2**: For any two periods $\pi_i < \pi_j$ with $\pi_j - \pi_i > \text{gap}_{\max}$:

$$
\text{att}_{\pi_i} + \text{att}_{\pi_j} \;\leq\; 1 + \sum_{m:\, \pi_i < \pi_m < \pi_j} \text{att}_{\pi_m},
$$

which ensures the time gap between two consecutive courses never exceeds $\text{gap}_{\max}$.

**Working Principle**: If a student attends classes in both $\pi_i$ and $\pi_j$ and the gap between them exceeds $gap_{\max}$, then at least one intermediate activity must also be attended. Repeatedly applying this rule ensures that the gap between any two consecutive attended periods stays within the allowed duration. If no intermediate period exists, the model forbids attending activities in both periods $\pi_i$ and $\pi_j$ (i.e., enforces $\text{att}_{\pi_i} + \text{att}_{\pi_j} \leq 1$).

> **Example.** A student has classes at P0, P2, P3, P6, with $\text{gap}_{\max} = 4$.
> Consecutive gaps: P0→P2 = 1, P2→P3 = 0, P3→P6 = 2 (all $\leq 4$).
> Check (P0, P6): P0→P6 = 6 > 4, at least one intermediate attended period needed: $1 + 1 \leq 1 + (\text{att}[P2] + \text{att}[P3]) = 1 + 2 = 3$, inequality holds.
> If the intermediate classes at P2 and P3 absent: Without the classes at P2, P3: $1 + 1 \leq 1 + (att[P2] + att[P3]) = 1 + 0  = 1$, inequality fails.

```python
# ... build attend[p] indicators ...
for lk in links:
    if lk[0] == 'lec':
        _, tv, ov = lk
        model.add(att >= tv + ov - 1)
    else:
        _, av = lk
        model.add(att >= av)
# Consecutive-gap elimination
periods = sorted(attend.keys())
for i in range(len(periods)):
    for j in range(i + 1, len(periods)):
        if periods[j] - periods[i] > max_gap:
            between = [attend[periods[m]] for m in range(i + 1, j)]
            if between:
                model.add(attend[periods[i]] + attend[periods[j]]
                          <= 1 + sum(between))
            else:
                model.add(attend[periods[i]] + attend[periods[j]] <= 1)
```

---

### S18. Improve ef Symmetry Breaking for Subgroups

> To grain scheduling, we further split the large student group into several smaller subgroups, from which many equivalent orderings for the same course assignments arise. We then impose a fixed ordering to eliminate these redundant solutions and hence accelerate the model: the earlier subgroup must take a superset of the courses taken by the later subgroup, forming a *superset ordering*.

As described above, each student type is split into $\lceil N_s / G \rceil$ sibling subgroups with identical `parent_type`. Let $s_0, s_1, \dots, s_{m-1}$ be the siblings, ordered by index.

For adjacent siblings $s_i, s_{i+1}$, for each course $c$, year $y$, semester $\sigma$:

$$
t_{s_i, c, y, \sigma} \;\geq\; t_{s_{i+1}, c, y, \sigma}
$$

> **KEY**: When all sibling subgroups share the same size $N_s$ (i.e., $N_{s_i}= N_{s_j}$ for any pairs of sibling subgroups), this constraint is an exact symmetry-breaking rule: the subgroups differ only by labels, so reordering them does not change the optimal result. For the case where $N_s$ leaves a remainder after splitting, subgroup sizes may differ, so the subgroups are no longer fully interchangeable, as swapping them would change enrolment counts. In this case, the constraint is slightly over-strict. However, under our balanced partitioning mechanism, subgroup sizes differ by at most 1, so the practical impact can be neglected.

```python
# Group subgroups by parent_type
sibling_groups = OrderedDict()
for s in inst.students:
    if s.parent_type is not None:
        sibling_groups.setdefault(s.parent_type, []).append(s.id)

for _, sib_ids in sibling_groups.items():
    for i in range(len(sib_ids) - 1):
        s_hi, s_lo = sib_ids[i], sib_ids[i + 1]
        # For each (cid, y, sem) in s_hi's take vars:
        #   model.add(take[s_hi, cid, y, sem] >= take[s_lo, cid, y, sem])
```

---

## 6. Course-Level Constraints

These constraints govern the logistics of course offerings: which semester a course runs in, how many sections are opened, capacity rules, and preventing internal timetable clashes within a single course.

> Source: `model/constraints_courses.py`

---

### C1. Course Offered in At Most One Semester

> **Plain English:** A course must “live” in **either Semester 1 or Semester 2**, not both. The course may still run in multiple academic years within the same semester (e.g., offered in Y3 and Y4, but always in semester 1.
> **Example:** If “Honours Analysis” is chosen for Semester 1, it can’t also appear in Semester 2 as another parallel offering. Students won’t be forced to guess “which semester version” to take.

Introduce $\beta_{c,\sigma} \in \{0,1\}$:

$$
\beta_{c,\sigma} \;\Leftrightarrow\; \bigvee_{y \in \mathcal{Y}} \alpha_{c,y,\sigma}
$$

$$
\sum_{\sigma \in \Sigma} \beta_{c,\sigma} \;\leq\; 1
$$

for each course $c$.

```python
ind = model.new_bool_var(f"sem_active[{c.id},S{sem}]")
link_or(model, act_vars, ind)
# ...
if sem_inds:
    model.add(sum(sem_inds) <= 1)
```

---

### C2. Active Consistency Across Years

> **Plain English:** If a course is offered in semester 1, it must be offered in *all* allowed years, not just a few(e.g., both Year 3 and Year 4). This ensures it is always available.
> **Example:** Suppose a course is allowed in Years 3–4. If it’s offered in Semester 1, then it’s offered in **both** Y3-S1 and Y4-S1 (not only Y3-S1).

Within the chosen semester, a course must be active in **all** allowed years or in none:

$$
\alpha_{c,y_1,\sigma} = \alpha_{c,y_2,\sigma} \quad \forall\, y_1, y_2 \in \mathcal{Y}
$$

for each course $c$, semester $\sigma$.

```python
for sem in all_semesters:
    act_vars = [vs.active[(c.id, y, sem)] for y in all_years if (c.id, y, sem) in vs.active]
    if len(act_vars) > 1:
        for av in act_vars[1:]:
            model.add(av == act_vars[0])
```

---

### C3. Global Offering Counts Per Semester

> **Plain English:** The department need  a specific number of gateway and optional courses to be offered each semester. For example, “offer exactly 3 gateway courses and 5 optional courses each semester.”
> **Example:** If the rule says “4 gateway per semester,” the solver can’t decide to offer only 2 gateway courses in Semester 1 just to avoid clashes.

$$
\sum_{c \in \mathcal{C}^{GW}} \beta_{c,\sigma} = G_\sigma^{GW}, \qquad \sum_{c \in \mathcal{C}^{OPT}} \beta_{c,\sigma} = G_\sigma^{OPT}
$$

for each semester $\sigma$.

```python
if gw:
    model.add(sum(gw) == gw_per_sem)
if opt:
    model.add(sum(opt) == opt_per_sem)
```

---

### C4. Open → Active (Implication)

> **Plain English:** If any timeslot of a course component is open (scheduled), the course itself must be marked as active. You can’t have a lecture running without the course being formally offered.

$$
o_{c,p,k} = 1 \;\Rightarrow\; \alpha_{c,y_k,\sigma_k} = 1
$$

for each $(c, p, k)$.

```python
for ov in olist:
    model.add_implication(ov, act)
```

---

### C5. Active → Section Count Bounds

> **Plain English:** When a course is active, each of its components must open the right number of timeslots. For example, a workshop that meets twice per week with 2–3 parallel sections needs 4–6 open timeslots total. When the course is inactive, everything is zero.
> **Example 1 (lecture):** A lecture component that meets **3 times per week** must open **exactly 3** lecture timeslots in that semester.
> **Example 2 (workshop):** A workshop meets **1 time per week** and needs **2–3 parallel sections** → the timetable must open **2 to 3** workshop slots (same week), so different students can attend different sections.

For each course $c$, component $p$, year $y$, semester $\sigma$:

$$
\underline{S}_p \cdot n_p^w \cdot \alpha_{c,y,\sigma} \;\leq\; \sum_{k:\, y_k=y,\, \sigma_k=\sigma} o_{c,p,k} \;\leq\; \overline{S}_p \cdot n_p^w \cdot \alpha_{c,y,\sigma}
$$

When $\alpha = 0$, all open vars must be 0. When $\alpha = 1$, the total open slots must be between `sections_min × number_per_week` and `sections_max × number_per_week`.

If no open vars exist and $\underline{S}_p \cdot n_p^w > 0$, force $\alpha = 0$.

```python
min_sec = comp.number_per_week * comp.sections_min
max_sec = comp.number_per_week * comp.sections_max
s = sum(olist)
model.add(s >= min_sec * act)
model.add(s <= max_sec * act)
```

---

### C6. Active → Minimum Attendance Threshold

> **Plain English:** A course can only be offered if there are enough students to fill the minimum required sections. For example, if a course needs at least 2 sections of 10 students each, at least 20 students must be enrolled.

For each course $c$, component $p$ with $\underline{Q}_p \cdot \underline{S}_p > 0$, each $(y, \sigma)$:

$$
\alpha_{c,y,\sigma} = 1 \;\Rightarrow\; \sum_s N_s \cdot t_{s,c,y,\sigma} \;\geq\; \underline{Q}_p \cdot \underline{S}_p
$$

A course can only be active if enough students (weighted) take it to fill the minimum sections.

```python
min_att = comp.sections_min * comp.section_cap_min
if min_att > 0:
    takes = take_by_ct.get((c.id, y, sem), [])
    if takes:
        model.add(sum(takes) >= min_att * act)
    else:
        model.add(act == 0)
```

---

### C7. Force Inactive When No Students Can Enroll

> **Plain English:** If no student type has a take-variable for a course in a given year/semester (no one is eligible to take it), force the course to be inactive.

$$
\alpha_{c,y,\sigma} = 0 \quad \text{if } \nexists\, s: t_{s,c,y,\sigma} \text{ exists}
$$

```python
for (cid, y, sem), act in vs.active.items():
    if not take_by_ct.get((cid, y, sem)):
        model.add(act == 0)
```

---

### C8. Sectioned Section Capacity

> **Plain English:** Each workshop section has a minimum and maximum capacity. If the section is open, the total number of assigned students (weighted by group size) must be within these limits. If the section is closed, no one can be assigned.
> **Example:** Workshop section cap is **10–25**. If “Tuesday 11:00 workshop section” is open, it must have between 10 and 25 students assigned. If that section is not open, assigned students must be exactly 0.

For each sectioned component $p \in \mathcal{P}_c^{\text{sec}}$, each timeslot key $k$:

$$
o_{c,p,k} = 0 \;\Rightarrow\; \sum_s N_s \cdot a_{s,c,p,k} = 0
$$

$$
o_{c,p,k} = 1 \;\Rightarrow\; \underline{Q}_p \;\leq\; \sum_s N_s \cdot a_{s,c,p,k} \;\leq\; \overline{Q}_p
$$

The assignment sums are **weighted** by $N_s$.

```python
s = sum(assigns)  # assigns stores N_s * a_{s,c,p,k} terms
model.add(s == 0).only_enforce_if(open_var.Not())
model.add(s <= comp.section_cap_max).only_enforce_if(open_var)
model.add(s >= comp.section_cap_min).only_enforce_if(open_var)
```

---

### C9. Non-Sectioned Component Capacity

> **Plain English:** For lecture-type components (where everyone attends the same slot), the total enrollment must be within capacity when the course is active.

For each non-sectioned component $p \notin \mathcal{P}_c^{\text{sec}}$, each timeslot key $k$:

$$
o_{c,p,k} = 1 \;\Rightarrow\; \underline{Q}_p \;\leq\; \sum_s N_s \cdot t_{s,c,y_k,\sigma_k} \;\leq\; \overline{Q}_p
$$

All students taking the course attend the same lecture slot, so the enrollment sum applies to each open slot.

```python
takes = take_by_ct.get((cid, k.year, k.semester), [])
if comp.section_cap_max < 999:
    model.add(s <= comp.section_cap_max).only_enforce_if(open_var)
if comp.section_cap_min > 0:
    model.add(s >= comp.section_cap_min).only_enforce_if(open_var)
```

---

### C10. Internal Course Conflict Avoidance

> **Plain English:** Two components of the *same* course (e.g., its lecture and its workshop) must not be scheduled at the same time on the same physical day. An exception: an ODD-week component and an EVEN-week component *can* share a slot since they never physically overlap.
> **Example:** (a)Not allowed: Lecture (every week) Mon 10:00 and Workshop (every week) Mon 10:00.
> (b) Workshop (odd weeks) Mon 10:00 and another component (even weeks) Mon 10:00 — because they alternate weeks, so students never need to be in two places at once.

For each course $c$ and each base slot $b = (y, \sigma, d, \pi)$, define:

$$
S_A = \sum_{\substack{p,k:\, \text{base}(k)=b,\; w_k=A}} o_{c,p,k}, \quad S_O = \sum_{\substack{w_k=O}} o_{c,p,k}, \quad S_E = \sum_{\substack{w_k=E}} o_{c,p,k}
$$

Constraints:

$$
S_A \leq 1, \quad S_O \leq 1, \quad S_E \leq 1
$$

$$
S_A + S_O \leq 1, \quad S_A + S_E \leq 1
$$

These ensure no two components of the same course occupy the same physical timeslot. ($O$ and $E$ are allowed to co-exist since they run on different physical weeks.)

```python
model.add(s_all <= 1)
model.add(s_odd <= 1)
model.add(s_evn <= 1)
model.add(s_all + s_odd <= 1)
model.add(s_all + s_evn <= 1)
```

---

### C11. Course Max Slots Per Day

> **Plain English:** A non-outside course cannot use more than a certain number of periods on the same day (e.g., max 2 hours per day). This prevents unreasonably long teaching blocks.
> **Example:** If `day_max = 2`, then a course cannot occupy more than **two separate hour-slots** on the same day (e.g., it could use 10:00 and 11:00, but not also 15:00). This is especially important for student experience and staff workload realism.

For each non-OUTSIDE course $c$, year $y$, semester $\sigma$, day $d$, physical week $\omega$:

For each period $\pi$, create indicator $\delta_{c,y,\sigma,\omega,d,\pi} \Leftrightarrow \bigvee_{p, k} o_{c,p,k}$ (over $k$ whose $(d_k, \pi_k) = (d, \pi)$ and $w_k$ compatible with $\omega$).

$$
\sum_{\pi} \delta_{c,y,\sigma,\omega,d,\pi} \;\leq\; \text{day}_{\max}
$$

(Only created when the number of candidate periods exceeds $\text{day}_{\max}$.)

```python
if len(period_ovs) <= max_per_day:
    continue
indicators = []
for p in period_ovs:
    ovs = period_ovs[p]
    if len(ovs) == 1:
        indicators.append(ovs[0])
    else:
        ind = model.new_bool_var(...)
        link_or(model, ovs, ind)
        indicators.append(ind)
model.add(sum(indicators) <= max_per_day)
```

---

## 7. Objective Function

The solver aims to *minimise* the difference between penalties and bonuses. Specifically, it tries to avoid timetable clashes while *maximising* rewards for students’ preferred course choices.

> Source: `model/objective.py`

$$
\min \quad \underbrace{\sum \text{Penalties}}_{\text{positive terms}} \;-\; \underbrace{\sum \text{Bonuses}}_{\text{negative terms}}
$$

---

### O1. Desired-Course Bonus

> The model grants bonuses when students do take their desired courses, encouraging preference satisfaction.

For each student type $s$ and each desired course $c \in \text{des}_s$:

$$
\text{Bonus}_{s,c,y,\sigma} = w_{\text{desire}} \cdot N_s \cdot t_{s,c,y,\sigma}
$$

**Total**:

$$
\text{Bonus}_{\text{total}} = w_{\text{desire}} \cdot \sum_{s} \sum_{c \in \text{des}_s} \sum_{y,\sigma} N_s \cdot t_{s,c,y,\sigma},
$$

with default weight $w_{\text{desire}} = 10$.

```python
for (sid, cid, y, sem), tv in vs.take.items():
    if cid in desired_by_student.get(sid, set()):
        bonuses.append(cfg.desire_bonus_weight * count_of[sid] * tv)
```

---

### O2. Activation Penalty

> For each semester, a small penalty is added for each active course, discouraging unnecessary course activations (e.g., opening low-demand courses).

For each active course, $c$:

$$
\text{Penalty}_{\text{act}} = w_{\text{act}} \cdot \sum_{c,y,\sigma} \alpha_{c,y,\sigma},
$$

with default weight $w_{\text{act}} = 1$.

```python
for av in vs.active.values():
    penalties.append(cfg.activation_penalty * av)
```

---

### O3. Conflict Penalty

> If two classes are scheduled for the same student at the same time, a conflict arises and is penalised with different severity weights: lecture–lecture clashes are the most severe, lecture–workshop clashes are moderate, and workshop–workshop clashes are the least severe.

For each student type $s$ and each base slot $b$, we create attendace Boolean indicators, $z^{att}_{s,c,p,k} \in \{0, 1\}$ (distinct from the $att$ variables in constraint S17).

- **Non-sectioned** component $(c, p)$ at base $b$:

$$
z^{\text{att}}_{s,c,p,k} = t_{s,c,y,\sigma} \;\wedge\; o_{c,p,k}.
$$

Implemented via `bool_and`: $z^{att} = 1$ when student takes the course and the slot is acive.

- **Sectioned** component $(c, p)$ at base $b$:

$$
z^{\text{att}}_{s,c,p,k} = a_{s,c,p,k}
$$

For each pair $(i, j)$ of attendance scheduled at the same $(s, b)$ with same week-patterns:

$$
z^{\text{cf}}_{s,b,i,j} = z^{\text{att}}_i \;\wedge\; z^{\text{att}}_j,
$$

$$
\text{Penalty}_{s,b,i,j} = \text{sev}(i,j) \cdot N_s \cdot z^{\text{cf}}_{s,b,i,j},
$$

where $z^{\text{cf}}_{s,b,i,j}=1$ iff clash occurs (student is scheduled to attend two classes $i$ and $j$ at same time), and $\text{sev}(i,j)$ denotes the conflict severity weight, as illustrated in the table below.

**Conflict Weighting Scheme**:

| Pair Type          | $\text{sev}$ | Default |
| ------------------ | :----------: | :-----: |
| Lecture–Lecture   |   $w_{LL}$   |   10   |
| Lecture–Workshop  |   $w_{LW}$   |    3    |
| Workshop–Workshop |   $w_{WW}$   |    1    |

Hence, for each student type $s$, each base slot $b$, each pair of attended activities $(i,j)$, the total conflict penalty is:

$$
\text{Penalty}_{\text{conflict}} = \sum_{s} \sum_{b} \sum_{\substack{(i,j):\\ \text{overlap}(w_i, w_j)}} \text{sev}(i,j) \cdot N_s \cdot z^{\text{cf}}_{s,b,i,j}
$$

where $\text{overlap}(w_1, w_2) = \text{true}$ iff two activities run in overlapping weeks: a weekly activity (A) overlaps with any pattern, and odd overlaps only with odd (similarly for even).

```python
for i in range(len(entries)):
    for j in range(i + 1, len(entries)):
        att_i, type_i, wp_i = entries[i]
        att_j, type_j, wp_j = entries[j]
        if not patterns_overlap(wp_i, wp_j):
            continue
        # ... determine severity ...
        both = bool_and(model, att_i, att_j, f"cf[{sid},{base},{i},{j}]")
        penalties.append(sev * weight * both)
```

---

### Complete Objective

$$
\boxed{\min \;\; w_{\text{act}} \sum_{c,y,\sigma} \alpha_{c,y,\sigma} \;+\; \sum_{s,b,(i,j)} \text{sev}(i,j) \cdot N_s \cdot z^{\text{cf}}_{s,b,i,j} \;-\; w_{\text{desire}} \sum_{s,c \in \text{des}_s,y,\sigma} N_s \cdot t_{s,c,y,\sigma}}
$$

---

## 8. Parameter Analysis and Discussion

This section discusses how the default parameter values interact and what trade-offs they create. It also analyses the precision of the aggregation model and when it matters.

### 8.1 Default Parameter Values

| Parameter                            | Symbol              | Value | Role                                               |
| ------------------------------------ | ------------------- | :---: | -------------------------------------------------- |
| `desire_bonus_weight`                | $w_{\text{desire}}$ |  10  | Bonus per student for taking a desired course      |
| `activation_penalty`                 | $w_{\text{act}}$    |   1   | Tie-breaker discouraging unnecessary activations   |
| `lecture_lecture_conflict_penalty`   | $w_{LL}$            |  10  | Penalty per student for a lecture–lecture clash   |
| `lecture_workshop_conflict_penalty`  | $w_{LW}$            |   3   | Penalty per student for a lecture–workshop clash  |
| `workshop_workshop_conflict_penalty` | $w_{WW}$            |   1   | Penalty per student for a workshop–workshop clash |

### 8.2 Observations

1. **Desire bonus vs. LL conflict**: $w_{\text{desire}} = w_{LL} = 10$. This means one lecture–lecture conflict for one student exactly offsets the bonus from one desired course for one student. The model is indifferent between (a) taking a desired course with one LL conflict and (b) not taking it. If desired courses should be preferred even at the cost of minor conflicts, consider $w_{\text{desire}} \in [12, 15]$.
2. **Severity ratios** $10 : 3 : 1$ reflect physical reality:
   
   - LL conflicts are worst (student misses an entire lecture, no alternative section).
   - LW conflicts are moderate (workshops often have multiple sections; a student with an LW clash may switch sections).
   - WW conflicts are lightest (same reasoning as LW; two workshops are most likely to have alternative sections).
3. **Activation penalty** $w_{\text{act}} = 1$ is two orders of magnitude smaller than other terms. It acts purely as a tie-breaker: among equally good schedules, prefer fewer active course-slots. This is appropriate.

### 8.3 Precision Assessment Summary

The table below classifies each constraint along two axes:

- **Model-level**: Is the formula mathematically correct given the decision variables? (Answer: always yes.)
- **Real-world level**: Does the model faithfully represent what happens for *individual* students? This is where the aggregation model introduces approximation — constraints that count students using weighted sums ($\sum N_s \cdot x_s$) are only as precise as the group size $G$.

| ID      | Constraint                          | Model-Level |     Real-World Level     |   Category   | Notes                                                                              |
| ------- | ----------------------------------- | :---------: | :----------------------: | :----------: | ---------------------------------------------------------------------------------- |
| S1      | Per-semester gateway count          |    Exact    |     Exact (per type)     |   Schedule   | BoolVar per type; every student in type satisfies                                  |
| S2      | Per-semester optional count         |    Exact    |     Exact (per type)     |   Schedule   | Same as S1                                                                         |
| S3      | Per-semester course count           |    Exact    |     Exact (per type)     |   Schedule   | Same as S1                                                                         |
| S4      | Per-semester credit bounds          |    Exact    |     Exact (per type)     |   Schedule   | Same as S1                                                                         |
| S5      | Total credits per year              |    Exact    |     Exact (per type)     |   Schedule   | Equality — exact                                                                  |
| S6      | Outside credits per year            |    Exact    |     Exact (per type)     |   Schedule   | Joint programmes only                                                              |
| S7      | Per-year gateway count              |    Exact    |     Exact (per type)     |   Schedule   | —                                                                                 |
| S8      | Per-year optional (conditional min) |    Exact    |     Exact (per type)     |   Schedule   | Indicator$h_{s,y}$ is exact                                                        |
| S9      | Per-year course count               |    Exact    |     Exact (per type)     |   Schedule   | —                                                                                 |
| S10     | Balanced credits                    |    Exact    |     Exact (per type)     |   Schedule   | Equality                                                                           |
| S11     | Total gateway requirement           |    Exact    |     Exact (per type)     |   Schedule   | —                                                                                 |
| S12     | Compulsory enrollment               |    Exact    |     Exact (per type)     |   Schedule   | —                                                                                 |
| S13     | Course uniqueness                   |    Exact    |     Exact (per type)     |   Schedule   | —                                                                                 |
| S14     | Sectioned attendance                |    Exact    |     Exact (per type)     |   Schedule   | Equality                                                                           |
| S15     | Take → Active                      |    Exact    |          Exact          |   Linkage   | Implication                                                                        |
| **S16** | **Enrollment caps**                 |  **Exact**  |  **Granular** (≤ $G$)  | **Capacity** | Enrollment quantised in blocks of$N_s$; error ≤ $G-1$                             |
| S17     | Max daily consecutive gap           |    Exact    |     Exact (per type)     |  Timetable  | Consecutive-gap formulation;`att` has no upper bound; solver keeps att=0 when free |
| **S18** | **Symmetry breaking**               |    Exact    | **Slightly over-strict** |   Symmetry   | Exact when siblings equal size; over-strict by ≤1 student                         |
| C1      | One semester per course             |    Exact    |          Exact          |  Structure  | —                                                                                 |
| C2      | Active consistency across years     |    Exact    |          Exact          |  Structure  | Equality                                                                           |
| C3      | Global offering counts              |    Exact    |          Exact          |  Structure  | Equality                                                                           |
| C4      | Open → Active                      |    Exact    |          Exact          |   Linkage   | Implication                                                                        |
| C5      | Section count bounds                |    Exact    |          Exact          |  Structure  | —                                                                                 |
| **C6**  | **Min attendance threshold**        |  **Exact**  |  **Granular** (≤ $G$)  | **Capacity** | Uses$\sum N_s \cdot t_{s}$; same quantisation as S16                               |
| C7      | Force inactive if no students       |    Exact    |          Exact          |   Linkage   | —                                                                                 |
| **C8**  | **Sectioned section capacity**      |  **Exact**  |  **Granular** (≤ $G$)  | **Capacity** | Uses$\sum N_s \cdot a_{s}$; same quantisation as S16                               |
| **C9**  | **Non-sectioned capacity**          |  **Exact**  |  **Granular** (≤ $G$)  | **Capacity** | Uses$\sum N_s \cdot t_{s}$; same quantisation as S16                               |
| C10     | Internal conflict avoidance         |    Exact    |          Exact          |  Timetable  | —                                                                                 |
| C11     | Course max slots per day            |    Exact    |          Exact          |  Timetable  | —                                                                                 |
| O1      | Desire bonus                        |    Exact    |     Granular (≤$G$)     |  Objective  | Partial enrollment possible with splitting                                         |
| O2      | Activation penalty                  |    Exact    |          Exact          |  Objective  | Independent of aggregation                                                         |
| O3      | Conflict penalty                    |    Exact    |     Granular (≤$G$)     |  Objective  | With splitting, different subgroups can avoid/incur conflicts independently        |

### 8.4 Aggregation Granularity Analysis

#### Three-Level Model Hierarchy

|               Level               | Description              |    $N_s$ per type    |   Capacity granularity   |    #Variables    |        Symmetry        |
| :--------------------------------: | ------------------------ | :-------------------: | :----------------------: | :--------------: | :--------------------: |
|         **I: Per-student**         | No aggregation ($G = 1$) |           1           |    Exact (1 student)    |       $O(       |    \text{students}    |
|      **II: Full aggregation**      | $G = 999$ (default)      | Up to total type size | Coarse (up to$\max N_s$) |     Minimal     |  Perfect within type  |
| **III: Controlled disaggregation** | $1 < G < \infty$         |       $\leq G$       |      Bounded by$G$      | Between I and II | Partial; broken by S18 |

#### Which Constraints Are Affected?

Only constraints that involve the **weighted sum** $\sum_s N_s \cdot x_s$ (where $x_s$ is a BoolVar) exhibit granularity effects. These are:

- **S16**: Course enrollment caps $\underline{E}_c \leq \sum N_s t_s \leq \overline{E}_c$
- **C6**: Minimum attendance threshold $\sum N_s t_s \geq \underline{Q}_p \underline{S}_p$
- **C8**: Sectioned section capacity $\underline{Q}_p \leq \sum N_s a_s \leq \overline{Q}_p$
- **C9**: Non-sectioned component capacity (same form as S16)
- **O1/O3**: Objective terms weighted by $N_s$

Per-type constraints (S1–S14, S17) are **never affected** by aggregation. They operate on BoolVar per type and are exact regardless of $G$.

#### Granularity Error Bound

Let $G$ be `max_group_size`. After splitting, every subgroup has $N_s \leq G$ students. The enrollment for any course is:

$$
E = \sum_{s} N_s \cdot t_s
$$

Since each $t_s \in \{0, 1\}$ and $N_s \leq G$, flipping one subgroup's decision changes $E$ by at most $G$. Therefore:

$$
\text{Granularity error} \leq G - 1
$$

Compared to a per-student model ($G = 1$), any capacity constraint can be "off" by at most $G - 1$ students.

**Proposition**: *For any instance with course cap $\overline{E}_c$ and section cap $\overline{Q}_p$, setting $G \leq \min(\overline{E}_c, \overline{Q}_p)$ guarantees that no type is entirely locked out of a course due to granularity. The resulting enrollment can always get within $G-1$ of the exact per-student optimum.*

#### Symmetry-Breaking Precision (S18)

Subgroups from the same parent type have sizes that differ by at most 1 (from `count % n_subs` remainder distribution). The symmetry-breaking constraint $t_{s_i} \geq t_{s_{i+1}}$ eliminates permutation-equivalent solutions.

- **Equal-size subgroups**: Exact symmetry breaking. Any optimal solution can be reordered to satisfy the constraint without changing any enrollment count.
- **Unequal-size subgroups** (differ by 1): Slightly over-strict. Swapping two subgroups' schedules changes enrollment by ±1, so the reordered solution might violate a tight capacity constraint. The impact is bounded by 1 student. This is **negligible** in practice.

#### Practical Impact Summary

| Scenario             |       Granularity       | Risk                                           | Recommendation                |
| -------------------- | :----------------------: | ---------------------------------------------- | ----------------------------- |
| $G = 999$ (no split) | $\max N_s$ (can be 100+) | Large type locked out if$N_s > \overline{E}_c$ | Use when caps are loose (999) |
| $G = 30$             |            30            | Moderate; good for large instances             | Good balance for typical caps |
| $G = 1$              |        1 (exact)        | None; per-student model                        | Slow for large instances      |
