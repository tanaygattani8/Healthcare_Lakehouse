# Databricks notebook source
# MAGIC %md
# MAGIC # P5b — a model that was actually built for this
# MAGIC
# MAGIC P5 tried `dslim/bert-base-NER`, trained on news text. Result: 1.28s per
# MAGIC piece (14.75 hours for the test set) and the "names" it found were
# MAGIC `Yu` and `Co` — wordpiece fragments, not `Lucius`.
# MAGIC
# MAGIC `obi/deid_roberta_i2b2` is trained on i2b2 de-identification data, which
# MAGIC is clinical notes labelled for exactly this task. The question is
# MAGIC whether it is better enough to be worth its cost.
# MAGIC
# MAGIC **The measure that matters is not "how many names did it find" but
# MAGIC "did it find the real patient's first name".** A model returning 37
# MAGIC confident fragments scores zero on the thing we care about.

# COMMAND ----------

# MAGIC %pip install transformers torch --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import time

from transformers import pipeline

# Real pieces, and the real first name of the patient each one came from, so
# we can ask the only question that matters: was that name found?
rows = (
    spark.sql("""
        SELECT c.chunk_text, p.FIRST AS real_name
        FROM healthcare_dev.silver.note_chunk c
        JOIN healthcare_dev.ops.heldout_patient h USING (patient_id)
        JOIN healthcare_dev.silver.patient p USING (patient_id)
        WHERE c.chunk_text LIKE concat('%', p.FIRST, '%')
        LIMIT 20
    """)
    .toPandas()
)
pieces = rows["chunk_text"].tolist()
names = rows["real_name"].tolist()
print(f"{len(pieces)} pieces, each known to contain its patient's first name")
print("names to find:", sorted(set(names)))

# COMMAND ----------

def evaluate(model_name: str) -> dict:
    load_start = time.time()
    try:
        ner = pipeline("ner", model=model_name, aggregation_strategy="simple")
    except Exception as exc:  # noqa: BLE001
        return {"model": model_name, "error": f"{type(exc).__name__}: {exc}"}
    load_seconds = time.time() - load_start

    run_start = time.time()
    outputs = [ner(piece) for piece in pieces]
    per_piece = (time.time() - run_start) / len(pieces)

    # Did it find the actual patient's name in the piece it came from?
    hits = 0
    found_words = []
    for output, real in zip(outputs, names):
        words = [h["word"].strip() for h in output]
        found_words.extend(words)
        if any(real.lower() in w.lower() or w.lower() in real.lower()
               for w in words if len(w) > 2):
            hits += 1

    return {
        "model": model_name,
        "load_seconds": round(load_seconds, 1),
        "seconds_per_piece": round(per_piece, 3),
        "hours_for_41592": round(per_piece * 41592 / 3600, 2),
        "real_names_found": f"{hits}/{len(pieces)}",
        "recall_on_patient_name": round(hits / len(pieces), 3),
        "sample_output": found_words[:10],
    }


results = [
    evaluate("obi/deid_roberta_i2b2"),
    evaluate("dslim/bert-base-NER"),
]
for r in results:
    print(json.dumps(r, indent=2))

# COMMAND ----------

dbutils.notebook.exit(json.dumps(results))
