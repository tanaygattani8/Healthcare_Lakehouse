"""Program 3: `ask` stores ai_query replies; `parse` finds the named text itself (D48)."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from scripts import dbx
from scripts.build_answer_key import find_all

MODEL = "databricks-meta-llama-3-3-70b-instruct"
OUT = Path("data/detections/llm.csv")

# No single quotes: this is pasted into SQL as a literal.
PROMPT = (
    "List every piece of private patient information in the clinical note below: "
    "person names, dates, ages, places and identifying numbers. "
    'Return ONLY a JSON array of objects like {"text": "...", "category": "..."} '
    "where category is one of name, date, age, geography, other_id. "
    "Copy each text exactly as it appears in the note. No explanation.\n\nNOTE:\n"
)

CATEGORIES = {"name", "date", "age", "geography", "other_id"}
ALIASES = {"location": "geography", "place": "geography", "person": "name",
           "id": "other_id", "identifier": "other_id"}


def spans_for(chunk: str, reply: str) -> tuple[list[tuple[int, int, str, str]], str]:
    """Every whole-word position of everything the model named, and how the reply went (E41)."""
    try:
        items = json.loads(reply[reply.index("["): reply.rindex("]") + 1])
    except ValueError:                   # no brackets, or not valid JSON
        return [], "bad_json"
    if not isinstance(items, list):
        return [], "bad_json"

    found = []
    missing = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        category = str(item.get("category", "")).strip().lower()
        category = ALIASES.get(category, category)
        if category not in CATEGORIES:
            category = "other_id"
        hits = find_all(chunk, text) if text else []
        missing += not hits
        found += [(start, end, category, text) for start, end in hits]
    return found, "not_in_note" if missing else "ok"


def ask() -> None:
    with dbx.connect() as conn, conn.cursor() as cur:
        # A failed call (rate limit, timeout) gets another go on the next run.
        cur.execute("DELETE FROM healthcare_dev.ops.llm_reply WHERE reply IS NULL")
        cur.execute("""
            SELECT DISTINCT c.patient_id FROM healthcare_dev.silver.note_chunk c
            JOIN healthcare_dev.ops.heldout_patient USING (patient_id)
            LEFT ANTI JOIN healthcare_dev.ops.llm_reply USING (patient_id, chunk_index)
            ORDER BY c.patient_id""")
        todo = [row[0] for row in cur.fetchall()]
        print(f"{len(todo)} patients with pieces still to ask")
        for n, patient_id in enumerate(todo, 1):
            # One statement per patient; no LIMIT near ai_query, it called every row (E43).
            cur.execute(f"""
                INSERT INTO healthcare_dev.ops.llm_reply
                SELECT patient_id, chunk_index, answer.result, answer.errorMessage
                FROM (
                    SELECT c.patient_id, c.chunk_index,
                           ai_query('{MODEL}', concat('{PROMPT}', c.chunk_text),
                                    modelParameters => named_struct('temperature', 0.0),
                                    failOnError => false) AS answer
                    FROM healthcare_dev.silver.note_chunk c
                    LEFT ANTI JOIN healthcare_dev.ops.llm_reply USING (patient_id, chunk_index)
                    WHERE c.patient_id = '{patient_id}')""")
            print(f"  {n}/{len(todo)} {cur.fetchone()}", flush=True)


def parse() -> None:
    with dbx.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT r.patient_id, c.char_start, c.chunk_text, r.reply, r.error
            FROM healthcare_dev.ops.llm_reply r
            JOIN healthcare_dev.silver.note_chunk c USING (patient_id, chunk_index)""")
        rows = cur.fetchall()

    status = {"ok": 0, "bad_json": 0, "not_in_note": 0, "call_failed": 0}
    spans = set()                # pieces overlap by 200 characters
    for patient_id, char_start, chunk, reply, error in rows:
        if error or reply is None:
            status["call_failed"] += 1
            continue
        found, how = spans_for(chunk, reply)
        status[how] += 1
        spans.update((patient_id, s + char_start, e + char_start, cat, text)
                     for s, e, cat, text in found)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["stage", "patient_id", "char_start", "char_end",
                         "phi_category", "surface_text"])
        writer.writerows(("llm", *span) for span in sorted(spans))

    # Report all of these: silently dropping broken replies flatters accuracy.
    print(f"{len(rows)} replies: {status}")
    print("'not_in_note' = at least one returned text is not in the piece verbatim")
    print(f"{len(spans)} spans written to {OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["ask", "parse"])
    {"ask": ask, "parse": parse}[parser.parse_args().step]()
