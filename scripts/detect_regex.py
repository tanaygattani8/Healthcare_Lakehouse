"""Program 1: find things that LOOK like private details, given no names.

The honest starting point. It cannot find names: there is no pattern that
matches 'Lucius' but not 'Patient'. That gap is the finding, not a flaw.

Dates it will find perfectly, and that is not to its credit either: every
date-shaped string in these notes is a real patient date (decision.md D52).

Runs locally on the test-set notes. Output: data/detections/regex.csv, which
sql/load_detections.sql loads into ops.detection_span.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from scripts import dbx

NOTES = Path("synthea/output/notes")
OUT = Path("data/detections/regex.csv")

# Written for clinical notes in general, not tuned to these ones. ssn, zip and
# contact never occur in Synthea notes (D50), so anything they match is a
# false alarm — which is worth knowing.
PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "date": re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    "zip": re.compile(r"\b\d{5}(?:-\d{4})?\b"),
    "contact": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b|\b\d{3}-\d{3}-\d{4}\b"),
}
# Safe Harbor only covers ages over 89, so the number is kept and the rest
# of "93 year-old" is not.
AGE = re.compile(r"\b(\d{2,3}) year-old")


def detect(note: str) -> list[tuple[int, int, str, str]]:
    found = [(m.start(), m.end(), category, m.group())
             for category, pattern in PATTERNS.items()
             for m in pattern.finditer(note)]
    found += [(m.start(1), m.end(1), "age", m.group(1))
              for m in AGE.finditer(note) if int(m.group(1)) > 89]
    return found


def main() -> None:
    with dbx.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT patient_id FROM healthcare_dev.ops.heldout_patient")
        heldout = {row[0] for row in cur.fetchall()}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["stage", "patient_id", "char_start", "char_end",
                         "phi_category", "surface_text"])
        for path in NOTES.glob("*.txt"):
            patient_id = path.name.rsplit("_", 1)[1][:-4]
            if patient_id not in heldout:
                continue
            note = path.read_text(encoding="utf-8", errors="replace")
            for start, end, category, text in detect(note):
                writer.writerow(["regex", patient_id, start, end, category, text])
                counts[category] = counts.get(category, 0) + 1

    print(f"{len(heldout)} test-set patients, written to {OUT}")
    for category, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {category:<8} {count:>6}")


if __name__ == "__main__":
    main()
