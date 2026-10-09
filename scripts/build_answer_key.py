"""Every real patient detail's position in every note: the silver.phi_span answer key."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from scripts import dbx

NOTES = Path("synthea/output/notes")

# Which patient column holds what kind of detail.
COLUMNS = {
    "name": ["FIRST", "MIDDLE", "LAST", "MAIDEN"],
    "geography": ["ADDRESS", "CITY", "COUNTY", "BIRTHPLACE"],
    "zip": ["ZIP"],
    "ssn": ["SSN"],
    "license": ["DRIVERS"],
    "other_id": ["PASSPORT"],
}

# No minimum length: it only dropped real two-letter names; whole-word matching is the guard.

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# Search each note once for date shapes, then look hits up (per-date passes took ~10 hours).
_MONTH = "(?:" + "|".join(MONTHS) + ")"
DATE_SHAPE = re.compile(
    r"(?<!\w)(?:"
    r"\d{4}-\d{2}-\d{2}"                 # 1971-05-01
    r"|\d{1,2}/\d{1,2}/\d{4}"            # 5/1/1971, 05/01/1971
    rf"|{_MONTH} \d{{1,2}}, \d{{4}}"     # May 1, 1971 / May 01, 1971
    rf"|\d{{1,2}} {_MONTH} \d{{4}}"      # 1 May 1971
    r")(?!\w)"
)


def check_we_can_see_real_data(cur) -> None:
    """Stop if masking would return '***' names or the row filter zero patients."""
    cur.execute("SELECT healthcare_dev.ops.is_cleared()")
    if not cur.fetchone()[0]:
        raise SystemExit(
            "Your clearance row is missing, so silver.patient would return "
            "'***' for every name.\n"
            "Fix it with:\n"
            "  INSERT INTO healthcare_dev.ops.phi_clearance "
            "VALUES (current_user(), 'full', '*');"
        )

    cur.execute("SELECT count(*) FROM healthcare_dev.silver.patient")
    visible = cur.fetchone()[0]
    if visible == 0:
        raise SystemExit(
            "silver.patient returns zero rows. The row filter is hiding them — "
            "check scope_state in ops.phi_clearance is '*' or 'Massachusetts'."
        )
    print(f"clearance ok, {visible} patients visible")


def date_forms(value: str) -> list[str]:
    """Every way a date gets written; a missed form is marked wrong for ever."""
    year, month, day = value.split("-")
    name = MONTHS[int(month) - 1]
    d, m = int(day), int(month)
    return [
        value,                                    # 1971-05-01
        f"{m}/{d}/{year}",                        # 5/1/1971
        f"{m:02d}/{d:02d}/{year}",                # 05/01/1971
        f"{name} {d}, {year}",                    # May 1, 1971
        f"{d} {name} {year}",                     # 1 May 1971
        f"{name} {d:02d}, {year}",                # May 01, 1971
    ]


def find_all(note: str, needle: str) -> list[tuple[int, int]]:
    """Every whole-word, case-sensitive position of `needle` (Ann must not match 'planned')."""
    pattern = re.compile(r"(?<!\w)" + re.escape(needle) + r"(?!\w)")
    return [(m.start(), m.end()) for m in pattern.finditer(note)]


def load_patients(limit: int) -> tuple[list[dict], dict[str, list[str]]]:
    """Patient details plus every visit date (88 of 89 dates in a note are visits)."""
    columns = sorted({c for cols in COLUMNS.values() for c in cols})
    select = ", ".join(columns)
    with dbx.connect() as conn, conn.cursor() as cur:
        check_we_can_see_real_data(cur)
        cur.execute(
            f"SELECT patient_id, cast(birth_date AS STRING) AS birth_date_str, "
            f"cast(death_date AS STRING) AS death_date_str, {select} "
            f"FROM healthcare_dev.silver.patient"
            + (f" LIMIT {limit}" if limit else "")
        )
        header = [d[0] for d in cur.description]
        patients = [dict(zip(header, row, strict=True)) for row in cur.fetchall()]

        # Chicago days, not UTC: notes are local time, and UTC lost 11% of dates (D35).
        ids = "', '".join(p["patient_id"] for p in patients)
        cur.execute(
            "SELECT patient_id, "
            "cast(to_date(from_utc_timestamp(started_at, 'America/Chicago')) AS STRING) "
            "FROM healthcare_dev.silver.encounter "
            f"WHERE patient_id IN ('{ids}')"
        )
        visits: dict[str, list[str]] = {}
        for patient_id, day in cur.fetchall():
            visits.setdefault(patient_id, []).append(day)

    return patients, visits


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0,
                        help="only do this many patients, for trying it out")
    parser.add_argument("--out", type=Path, default=Path("data/phi_span.csv"))
    args = parser.parse_args()

    patients, visits = load_patients(args.limit)
    notes = {p.name.rsplit("_", 1)[1][:-4]: p for p in NOTES.glob("*.txt")}
    print(f"{len(patients)} patients, {len(notes)} note files on disk")

    spans: list[tuple] = []
    missing_note = 0

    for patient in patients:
        path = notes.get(patient["patient_id"])
        if path is None:
            missing_note += 1
            continue
        note = path.read_text(encoding="utf-8", errors="replace")

        for category, columns in COLUMNS.items():
            # A set: some patients have FIRST == MIDDLE, which would double-count positions.
            values = {(patient.get(c) or "").strip() for c in columns} - {""}
            for value in sorted(values):
                for start, end in find_all(note, value):
                    spans.append((patient["patient_id"], start, end,
                                  category, value))

        # A set: same-day encounters and padded/unpadded forms repeat positions.
        dates = {patient.get("birth_date_str"), patient.get("death_date_str")}
        dates.update(visits.get(patient["patient_id"], []))
        wanted = {form for d in dates if d for form in date_forms(d)}
        for match in DATE_SHAPE.finditer(note):
            if match.group() in wanted:
                spans.append((patient["patient_id"], match.start(),
                              match.end(), "date", match.group()))

        # Safe Harbor only covers ages over 89.
        for match in re.finditer(r"\b(\d{2,3}) year-old", note):
            if int(match.group(1)) > 89:
                spans.append((patient["patient_id"], match.start(1),
                              match.end(1), "age", match.group(1)))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["patient_id", "char_start", "char_end",
                         "phi_category", "surface_text"])
        writer.writerows(spans)

    by_category: dict[str, int] = {}
    for span in spans:
        by_category[span[3]] = by_category.get(span[3], 0) + 1

    with_spans = len({s[0] for s in spans})
    print(f"\n{len(spans)} spans written to {args.out}")
    for category, count in sorted(by_category.items(), key=lambda x: -x[1]):
        print(f"  {category:<12} {count:>7}")
    duplicates = len(spans) - len({s[:3] for s in spans})
    print(f"\npositions recorded more than once: {duplicates}")
    if missing_note:
        print(f"patients with no note file: {missing_note}")
    print(f"PATIENTS WITH NO SPANS AT ALL: {len(patients) - with_spans - missing_note}")
    if "date" not in by_category:
        print("\n*** NO DATES FOUND. The notes write dates in a format")
        print("*** date_forms() does not produce. Open a note and look")
        print("*** before going any further.")


if __name__ == "__main__":
    main()
