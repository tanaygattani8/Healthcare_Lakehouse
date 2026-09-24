"""Find every real patient detail inside every note, and write down where.

Reads the notes from synthea/output/notes/ on this machine and the patient
details from silver.patient. Writes a CSV that becomes silver.phi_span — the
answer sheet every detection program is marked against.

Run it on ten patients first and read the output. Phase 1's worst bug
(errors.md E3) was found by reading actual output rather than trusting config.
"""

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

# No minimum length. There used to be one (3 characters, "Mr would hit every
# line") and it only ever dropped real names: 7 two-letter first names, 1,898
# occurrences in their own patients' notes and ZERO in anyone else's.
# find_all() is whole-word and case-sensitive, which is the real guard.

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# Anything shaped like one of the date_forms() below. The note is searched
# once for this, and each hit is looked up in the patient's set of real dates.
# Searching once per date per form instead took ~10 hours on the full corpus:
# a patient with 500 visits meant 3,000 passes over a 3 MB note.
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
    """Stop if the 3a masking would hand us '***' instead of real names.

    Without this the script happily builds an answer sheet full of '***' and
    every number for the rest of the phase is meaningless. The row filter is
    checked too: a wrong scope_state returns zero patients, not an error.
    """
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
    """A birthday gets written several ways. Miss one and every program is
    marked wrong on it for ever."""
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
    """Every place `needle` appears as a whole word.

    Whole-word matters: a patient called Ann would otherwise match inside
    'announced', 'cannot' and 'planned'.
    """
    pattern = re.compile(r"(?<!\w)" + re.escape(needle) + r"(?!\w)")
    return [(m.start(), m.end()) for m in pattern.finditer(note)]


def load_patients(limit: int) -> tuple[list[dict], dict[str, list[str]]]:
    """Patient details, plus every visit date per patient.

    Visit dates matter more than anything else here. Measured on one note:
    89 dates present, of which birth date is ONE. Building the answer sheet
    from silver.patient alone would mark 88 of 89 real dates as "not private",
    so every program would be punished for finding them.
    """
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

        # America/Chicago, not UTC. Synthea wrote the notes in local time but
        # the CSV stores UTC with a Z, so an evening appointment in Chicago is
        # the next day in UTC. Using to_date() directly cost 11% of all dates
        # overall and 94% for one patient, because Synthea gives each patient
        # a consistent appointment hour — so the error clusters per patient
        # instead of averaging out. The timezone is the one pinned in
        # synthea/Dockerfile (decision.md D35).
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
            # A set: 3 patients have FIRST == MIDDLE, which wrote every one of
            # their name positions twice (902 duplicate rows). A program that
            # finds the name once would have been marked as missing it once.
            values = {(patient.get(c) or "").strip() for c in columns} - {""}
            for value in sorted(values):
                for start, end in find_all(note, value):
                    spans.append((patient["patient_id"], start, end,
                                  category, value))

        # Birth, death, and every visit. A set, because a patient can have
        # several encounters on one day and 12/11/1971 is both the padded and
        # unpadded form — either would record the same position twice.
        dates = {patient.get("birth_date_str"), patient.get("death_date_str")}
        dates.update(visits.get(patient["patient_id"], []))
        wanted = {form for d in dates if d for form in date_forms(d)}
        for match in DATE_SHAPE.finditer(note):
            if match.group() in wanted:
                spans.append((patient["patient_id"], match.start(),
                              match.end(), "date", match.group()))

        # Safe Harbor only requires suppressing ages OVER 89. An age of 55 is
        # not an identifier, so matching every "NN year-old" would flood the
        # answer sheet with things that are not private.
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
