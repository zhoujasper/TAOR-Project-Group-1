# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages


# -----------------------------
# Config
# -----------------------------

FILE_DIR = "run_demo_baseline_combine_2026_03_03_19_51_52"

CSV_PATH = f"output/{FILE_DIR}/timetable.csv"
YEAR = 3
COURSE_PREFIX = ["MATH", "ECON", "PHIL", "PHY", "CS", "BUS"]
DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri"]


# -----------------------------
# Helpers
# -----------------------------
def parse_time_range(time_str: str):
    """
    Parse "9:00-10:00" or "09:00-10:00" -> (start_hour_float, end_hour_float)
    """
    a, b = str(time_str).split("-")

    def to_hours(t):
        h, m = t.split(":")
        return int(h) + int(m) / 60.0

    return to_hours(a), to_hours(b)


def text_color_for_facecolor(rgba):
    """
    Choose black/white text based on luminance for readability.
    """
    r, g, b, a = rgba
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "black" if lum > 0.60 else "white"


def build_color_map(course_ids):
    """
    Build stable course_id -> color mapping (tab20).
    """
    cmap = plt.get_cmap("tab20")
    return {cid: cmap(i % cmap.N) for i, cid in enumerate(sorted(course_ids))}


def draw_semester(sub: pd.DataFrame, semester: int, course_color: dict, out_png: str):
    """
    Draw colored block timetable for one semester and save to PNG.
    Even weeks are hatched.
    Overlaps in identical time-slot on same day are split into subcolumns.
    """
    day_to_x = {d: i for i, d in enumerate(DAY_ORDER)}

    # Fixed time range 9:00–18:00
    start_min = 9.0
    end_max = 18.0

    # Hour grid
    hours = np.arange(start_min, end_max + 1, 1)

    # Handle overlaps:
    # same day + same time interval -> multiple sessions: split day column into n subcolumns
    key_cols = ["day", "start_h", "end_h"]
    sub = sub.sort_values(["day", "start_h", "course_id", "component_id", "week_pattern"]).copy()
    sub["slot_n"] = sub.groupby(key_cols)["course_id"].transform("count")
    sub["slot_i"] = sub.groupby(key_cols).cumcount()

    # Figure
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

    # Draw blocks
    pad_x = 0.03
    pad_y = 0.04

    for _, r in sub.iterrows():
        day = str(r["day"])
        if day not in day_to_x:
            continue

        x0 = float(day_to_x[day])
        y0 = float(r["start_h"])
        duration = float(r["end_h"] - r["start_h"])

        n = int(r["slot_n"])
        i = int(r["slot_i"])
        w = 1.0 / max(1, n)

        rect_x = x0 + i * w + pad_x * w
        rect_w = w * (1 - 2 * pad_x)
        rect_y = y0 + pad_y
        rect_h = duration * (1 - 2 * pad_y)

        cid = str(r["course_id"])
        face = course_color.get(cid, (0.4, 0.4, 0.4, 1.0))

        # Hatch for even weeks
        hatch = "///" if str(r["week_pattern"]) == "even_weeks" else None

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

        # Text
        label = f'{r["course_id"]}\n{r["component_id"]} · {r["week_label"]}'
        tc = text_color_for_facecolor(face)
        ax.text(
            rect_x + rect_w / 2,
            rect_y + rect_h / 2,
            label,
            ha="center",
            va="center",
            fontsize=8.5,
            color=tc,
            wrap=True,
        )

    # Title
    # Use prefix from the data if available, otherwise fallback
    prefixes_in_data = sorted(set(c.split("_")[0] for c in sub["course_id"].astype(str).unique() if c))
    prefix_label = ", ".join(prefixes_in_data) if prefixes_in_data else "ALL"
    ax.set_title(f"Year {YEAR} {prefix_label} Timetable — Semester {semester}", fontsize=15, pad=22)

    # Legend (course_id — course_name) + Even weeks
    course_meta = (
        sub[["course_id", "course_name"]]
        .drop_duplicates()
        .sort_values("course_id")
        .reset_index(drop=True)
    )

    handles, labels = [], []
    for _, row in course_meta.iterrows():
        cid = str(row["course_id"])
        name = str(row["course_name"])
        handles.append(patches.Patch(facecolor=course_color[cid], edgecolor="none"))
        labels.append(f"{cid} — {name}")

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

    # Clean spines
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.tight_layout()
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    return fig


# -----------------------------
# Main
# -----------------------------
def main():
    Path(f"visulisation/{FILE_DIR}").mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(CSV_PATH)

    for col in COURSE_PREFIX:
        # Filter: Year 3 + prefix
        sub = df[
            (df["year"] == YEAR)
            & (df["course_id"].astype(str).str.startswith(col))
        ].copy()

        if sub.empty:
            print(f"No data for prefix {col}, skipping.")
            continue

        # Per-prefix output paths
        out_png_s1 = f"visulisation/{FILE_DIR}/year{YEAR}_{col}_sem1.png"
        out_png_s2 = f"visulisation/{FILE_DIR}/year{YEAR}_{col}_sem2.png"
        out_pdf_all = f"visulisation/{FILE_DIR}/year{YEAR}_{col}_sem1_sem2.pdf"

        # Keep Mon-Fri only
        sub = sub[sub["day"].isin(DAY_ORDER)].copy()

        # Time parsing
        sub[["start_h", "end_h"]] = sub["time"].apply(lambda s: pd.Series(parse_time_range(s)))

        # Week pattern labels (English)
        week_label = {
            "every_week": "Weekly",
            "even_weeks": "Even weeks",
            "odd_weeks": "Odd weeks",
        }
        sub["week_label"] = sub["week_pattern"].map(week_label).fillna(sub["week_pattern"].astype(str))

        # Stable color mapping across both semesters
        course_color = build_color_map(sub["course_id"].unique())

        # Draw two semesters
        s1 = sub[sub["semester"] == 1].copy()
        s2 = sub[sub["semester"] == 2].copy()

        fig1 = draw_semester(s1, 1, course_color, out_png_s1)
        fig2 = draw_semester(s2, 2, course_color, out_png_s2)

        # Export combined PDF
        with PdfPages(out_pdf_all) as pdf:
            pdf.savefig(fig1)
            pdf.savefig(fig2)

        plt.close(fig1)
        plt.close(fig2)

        print(f"Saved ({col}):")
        print(" -", out_png_s1)
        print(" -", out_png_s2)
        print(" -", out_pdf_all)


if __name__ == "__main__":
    main()