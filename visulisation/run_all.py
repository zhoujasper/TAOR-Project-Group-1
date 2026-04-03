# -*- coding: utf-8 -*-
"""
Run output_school.py and output_student.py for ALL output folders.
"""
import os
import sys
from pathlib import Path
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT / "visulisation"))

import output_school
import output_student

OUTPUT_DIR = PROJECT_ROOT / "output"


def main():
    folders = sorted(
        f.name for f in OUTPUT_DIR.iterdir() if f.is_dir()
    )

    print(f"Found {len(folders)} output folder(s):\n")
    for folder in folders:
        print(f"  {folder}")
    print()

    for folder in folders:
        timetable_csv = OUTPUT_DIR / folder / "timetable.csv"
        student_csv = OUTPUT_DIR / folder / "student_assignments.csv"

        print(f"\n{'=' * 60}")
        print(f"Processing: {folder}")
        print(f"{'=' * 60}")

        # --- school timetable ---
        if timetable_csv.exists():
            print(f"\n[School Timetable]")
            output_school.FILE_DIR = folder
            output_school.CSV_PATH = f"output/{folder}/timetable.csv"
            output_school.OUT_DIR = f"visulisation/{folder}/school"
            output_school.main()
            plt.close("all")
        else:
            print(f"  Skipping school: timetable.csv not found")

        # --- student timetable ---
        if student_csv.exists():
            print(f"\n[Student Timetable]")
            output_student.FILE_DIR = folder
            output_student.CSV_PATH = f"output/{folder}/student_assignments.csv"
            output_student.OUT_DIR = f"visulisation/{folder}/student"
            output_student.main()
            plt.close("all")
        else:
            print(f"  Skipping student: student_assignments.csv not found")

    print(f"\n{'=' * 60}")
    print("All done!")


if __name__ == "__main__":
    main()
