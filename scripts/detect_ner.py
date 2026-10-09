"""Program 2: obi/deid_roberta_i2b2 run locally (D51); needs torch and transformers."""

from __future__ import annotations

import argparse
import csv
import hashlib
import time
from pathlib import Path

NOTES = Path("synthea/output/notes")
OUT = Path("data/detections/ner.csv")
MODEL = "obi/deid_roberta_i2b2"

# Same pieces as silver/note_chunk.sql: 2,000 characters every 1,800.
PIECE, STEP = 2000, 1800

# i2b2 labels to answer-key categories; STAFF names identify too.
KIND = {
    "PATIENT": "name", "STAFF": "name",
    "DATE": "date", "AGE": "age",
    "LOC": "geography", "HOSP": "geography", "PATORG": "geography",
    "ID": "other_id", "PHONE": "other_id", "EMAIL": "other_id", "OTHERPHI": "other_id",
}


def heldout(notes: dict[str, Path]) -> list[str]:
    """The 25 test patients, computed as sql/heldout_patient.sql picks them."""
    return sorted(notes, key=lambda p: hashlib.md5(p.encode()).hexdigest())[:25]


def merge(tokens: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Join B-/I-/L-/U- tokens of one kind into spans, per kind so fragments aren't split (E45)."""
    last: dict[str, list] = {}
    spans: list[list] = []
    for start, end, kind in sorted(tokens):
        current = last.get(kind)
        if current and start <= current[1] + 1:
            current[1] = max(current[1], end)
        else:
            last[kind] = [start, end, kind]
            spans.append(last[kind])
    return sorted((s, e, k) for s, e, k in spans)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pieces", type=int, default=0,
                        help="time this many pieces of one patient, save nothing")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForTokenClassification.from_pretrained(MODEL).eval()
    labels = model.config.id2label

    def tag(text: str) -> tuple[set[tuple[int, int, str]], int]:
        # Explicit 512-token windows: a truncating pipeline drops text silently.
        enc = tokenizer(text, return_offsets_mapping=True, return_overflowing_tokens=True,
                        truncation=True, max_length=512, stride=64,
                        padding=True, return_tensors="pt")
        offsets = enc.pop("offset_mapping")
        enc.pop("overflow_to_sample_mapping")
        with torch.no_grad():
            predicted = model(**enc).logits.argmax(-1)
        found = set()
        for window_offsets, window_labels in zip(offsets, predicted, strict=True):
            for (s, e), label_id in zip(window_offsets.tolist(), window_labels.tolist(),
                                        strict=True):
                label = labels[label_id]
                if s != e and label != "O":
                    found.add((s, e, KIND.get(label.split("-", 1)[1], "other_id")))
        return found, len(offsets)

    notes = {p.name.rsplit("_", 1)[1][:-4]: p for p in NOTES.glob("*.txt")}
    patients = heldout(notes)
    done = set()
    if OUT.exists() and not args.pieces:
        with OUT.open(encoding="utf-8") as fh:
            done = {row["patient_id"] for row in csv.DictReader(fh)}
    todo = [p for p in patients if p not in done]
    print(f"{len(patients)} test patients, {len(done)} already in {OUT}, {len(todo)} to do")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not OUT.exists():
        OUT.write_text("stage,patient_id,char_start,char_end,phi_category,surface_text\n",
                       encoding="utf-8")

    started, pieces_done, over_512 = time.time(), 0, 0
    for n, patient_id in enumerate(todo[:1] if args.pieces else todo, 1):
        # Read exactly as build_answer_key.py does, so positions line up.
        note = notes[patient_id].read_text(encoding="utf-8", errors="replace")
        starts = range(0, max(len(note), 1), STEP)
        if args.pieces:
            starts = starts[:args.pieces]

        tokens = []
        for start in starts:
            found, windows = tag(note[start:start + PIECE])
            over_512 += windows > 1
            tokens += [(s + start, e + start, k) for s, e, k in found]
        pieces_done += len(starts)
        spans = merge(tokens)
        rate = (time.time() - started) / pieces_done

        if args.pieces:
            kinds = {k: sum(1 for s in spans if s[2] == k) for k in set(KIND.values())}
            print(f"{len(starts)} pieces, {rate:.2f}s each, over 512 tokens: {over_512}")
            print(f"found: {kinds}")
            print(f"names: {sorted({note[s:e] for s, e, k in spans if k == 'name'})[:10]}")
            left = sum(len(range(0, len(notes[p].read_text(encoding='utf-8')), STEP))
                       for p in patients)
            print(f"all 25 patients: {left} pieces, about {left * rate / 3600:.1f} hours")
            return

        # One patient at a time, flushed, so a crash loses one patient.
        with OUT.open("a", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(("ner", patient_id, s, e, k, note[s:e])
                                     for s, e, k in spans)
        print(f"{n}/{len(todo)} {len(starts)} pieces, {len(spans)} spans, "
              f"{rate:.2f}s/piece, over 512 tokens so far: {over_512}", flush=True)


if __name__ == "__main__":
    main()
