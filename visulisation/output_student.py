# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages


# ==============================
# Config
# ==============================

FILE_DIR = "run_demo_baseline_2026_03_03_19_36_03"

CSV_PATH = f"output/{FILE_DIR}/student_assignments.csv"
YEARS = [3, 4]
DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri"]

# Number of student types to randomly sample PER PROGRAMME.
# Set to None or 0 to generate for ALL student types in each programme.
N_SAMPLES_PER_PROGRAMME = 2

# Random seed for reproducibility (set to None for different results each run)
RANDOM_SEED = 42

OUT_DIR = f"visulisation/{FILE_DIR}/student"


# ==============================
# Helpers
# ==============================

def parse_time_range(time_str: str):
    """Parse '9:00-10:00' -> (start_hour_float, end_hour_float)."""
    a, b = str(time_str).split("-")

    def to_hours(t):
        h, m = t.split(":")
        return int(h) + int(m) / 60.0

    return to_hours(a), to_hours(b)


def text_color_for_facecolor(rgba):
    """Choose black or white text based on background luminance."""
    r, g, b, a = rgba
    lum = 0.2126*r + 0.7152*g + 0.0722*b
    return "black" if lum > 0.6 else "white"


def build_color_map(course_ids):
    """Build a stable course_id -> colour mapping using tab20 colormap."""
    cmap = plt.get_cmap("tab20")
    return {cid: cmap(i % cmap.N) for i, cid in enumerate(sorted(course_ids))}


# ==============================
# Drawing
# ==============================

def draw_semester(df_sem: pd.DataFrame, year: int, semester: int, student_id: str,
                  course_color: dict, out_png: str):
    """Draw a coloured block timetable for one semester and save to PNG."""

    if df_sem.empty:
        print(f"  Semester {semester}: no courses, skipping.")
        return None

    day_to_x = {d: i for i, d in enumerate(DAY_ORDER)}

    # Fixed time range 9:00-18:00
    start_min = 9.0
    end_max = 18.0
    hours = np.arange(start_min, end_max + 1, 1)

    # Handle overlapping time-slots on the same day
    key_cols = ["day", "start_h", "end_h"]
    df_sem = df_sem.sort_values(
        ["day", "start_h", "course_id", "component_id", "week_pattern"]
    ).copy()

    df_sem["slot_n"] = df_sem.groupby(key_cols)["course_id"].transform("count")
    df_sem["slot_i"] = df_sem.groupby(key_cols).cumcount()

    fig, ax = plt.subplots(figsize=(13.5, 7.5))
    ax.set_xlim(0, len(DAY_ORDER))
    ax.set_ylim(end_max, start_min)  # invert so earlier time at top

    # X axis (days)
    ax.set_xticks([i + 0.5 for i in range(len(DAY_ORDER))])
    ax.set_xticklabels(DAY_ORDER, fontsize=11)
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", length=0)

    # Y axis (hours)
    ax.set_yticks(hours)
    ax.set_yticklabels([f"{int(h):02d}:00" for h in hours], fontsize=10)
    ax.tick_params(axis="y", length=0)

    # Grid lines
    for x in range(len(DAY_ORDER) + 1):
        ax.axvline(x, linewidth=1.0, alpha=0.15)
    for h in hours:
        ax.axhline(h, linewidth=1.0, alpha=0.12)

    pad_x, pad_y = 0.03, 0.04

    for _, r in df_sem.iterrows():
        day = r["day"]
        if day not in day_to_x:
            continue

        x0 = float(day_to_x[day])
        y0 = float(r["start_h"])
        duration = float(r["end_h"] - r["start_h"])

        n = int(r["slot_n"])
        i = int(r["slot_i"])
        width = 1.0 / max(1, n)

        rect_x = x0 + i * width + pad_x * width
        rect_w = width * (1 - 2 * pad_x)
        rect_y = y0 + pad_y
        rect_h = duration * (1 - 2 * pad_y)

        cid = r["course_id"]
        face = course_color.get(cid, (0.5, 0.5, 0.5, 1))

        hatch = "///" if r["week_pattern"] == "even_weeks" else None

        rect = patches.Rectangle(
            (rect_x, rect_y),
            rect_w,
            rect_h,
            linewidth=1.2,
            edgecolor="white",
            facecolor=face,
            hatch=hatch,
        )
        ax.add_patch(rect)

        label = f"{cid}\n{r['component_id']} · {r['week_label']}"

        ax.text(
            rect_x + rect_w / 2,
            rect_y + rect_h / 2,
            label,
            ha="center",
            va="center",
            fontsize=8.5,
            color=text_color_for_facecolor(face),
            wrap=True,
        )

    ax.set_title(
        f"Year {year} Student Timetable \u2014 {student_id} \u2014 Semester {semester}",
        fontsize=15,
        pad=22,
    )

    # Legend
    meta = (
        df_sem[["course_id", "course_name"]]
        .drop_duplicates()
        .sort_values("course_id")
    )

    handles, labels = [], []

    for _, row in meta.iterrows():
        cid = row["course_id"]
        handles.append(patches.Patch(facecolor=course_color[cid], edgecolor="none"))
        labels.append(f"{cid} — {row['course_name']}")

    handles.append(patches.Patch(facecolor="white", edgecolor="black", hatch="///"))
    labels.append("Even weeks (hatched)")

    ax.legend(
        handles,
        labels,
        loc="upper left",
        bbox_to_anchor=(1.01, 1.02),
        frameon=True,
        fontsize=8,
        title="Legend",
        title_fontsize=9,
    )

    # Remove spines
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.tight_layout()
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    return fig


# ==============================
# Main
# ==============================

def main():
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(CSV_PATH)

    # Validate required columns
    required_cols = [
        "year", "student_type_id", "programme", "semester",
        "day", "time", "course_id",
        "course_name", "component_id",
        "week_pattern",
    ]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")

    rng = np.random.default_rng(RANDOM_SEED)

    # Group student types by programme
    prog_types = (
        df[["programme", "student_type_id"]]
        .drop_duplicates()
        .groupby("programme")["student_type_id"]
        .apply(lambda x: sorted(x))
        .to_dict()
    )

    # For each programme, randomly sample N_SAMPLES_PER_PROGRAMME types
    selected_types = []
    for prog in sorted(prog_types):
        types = prog_types[prog]
        if N_SAMPLES_PER_PROGRAMME and N_SAMPLES_PER_PROGRAMME < len(types):
            chosen = sorted(rng.choice(types, size=N_SAMPLES_PER_PROGRAMME, replace=False))
        else:
            chosen = types
        selected_types.extend(chosen)
        print(f"Programme '{prog}': {len(types)} type(s) -> selected {chosen}")

    print(f"\nTotal selected student types: {len(selected_types)}")
    print(f"Years: {YEARS}\n")

    # Iterate over each year x selected student type
    for year in YEARS:
        for sid in selected_types:
            print(f"--- Year {year} / {sid} ---")

            stu = df[
                (df["year"] == year) & (df["student_type_id"] == sid)
            ].copy()

            # Keep Mon-Fri only
            stu = stu[stu["day"].isin(DAY_ORDER)].copy()

            # De-duplicate by timeslot key if present
            if "timeslot_key_id" in stu.columns:
                stu = stu.drop_duplicates(subset=["timeslot_key_id"])

            if stu.empty:
                print(f"  No timetable data, skipping.")
                continue

            # Parse time strings
            stu[["start_h", "end_h"]] = stu["time"].apply(
                lambda s: pd.Series(parse_time_range(s))
            )

            # Week pattern labels
            week_label_map = {
                "every_week": "Weekly",
                "even_weeks": "Even weeks",
                "odd_weeks": "Odd weeks",
            }
            stu["week_label"] = stu["week_pattern"].map(week_label_map).fillna(
                stu["week_pattern"]
            )

            # Colour mapping
            course_color = build_color_map(stu["course_id"].unique())

            # Output paths: OUT_DIR/year{Y}_{sid}_sem{S}.png
            out_png_s1 = f"{OUT_DIR}/year{year}_{sid}_sem1.png"
            out_png_s2 = f"{OUT_DIR}/year{year}_{sid}_sem2.png"
            out_pdf    = f"{OUT_DIR}/year{year}_{sid}_sem1_sem2.pdf"

            # Draw two semesters
            s1 = stu[stu["semester"] == 1].copy()
            s2 = stu[stu["semester"] == 2].copy()

            fig1 = draw_semester(s1, year, 1, sid, course_color, out_png_s1)
            fig2 = draw_semester(s2, year, 2, sid, course_color, out_png_s2)

            # Export combined PDF
            with PdfPages(out_pdf) as pdf:
                if fig1:
                    pdf.savefig(fig1)
                if fig2:
                    pdf.savefig(fig2)

            if fig1:
                plt.close(fig1)
            if fig2:
                plt.close(fig2)

            print(f"  Saved:")
            print(f"    - {out_png_s1}")
            print(f"    - {out_png_s2}")
            print(f"    - {out_pdf}")


if __name__ == "__main__":
    main()