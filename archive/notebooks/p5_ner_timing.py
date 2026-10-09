# Databricks notebook source
# MAGIC %md
# MAGIC # P5 — can a name-finding model run here, and how slow is it?
# MAGIC
# MAGIC Phase 3b step 0. Three questions, in order of how likely they are to
# MAGIC stop the whole thing:
# MAGIC
# MAGIC 1. Does `pip install transformers torch` work on serverless?
# MAGIC 2. Can the model be **downloaded**? The spec says outbound internet is
# MAGIC    restricted, and Hugging Face is outbound internet.
# MAGIC 3. How long does one 2,000-character piece take?
# MAGIC
# MAGIC Question 3 is the decision. There are **41,592 pieces** in the test set.
# MAGIC At 0.1s that is 70 minutes; at 1s it is 11.5 hours.

# COMMAND ----------

# MAGIC %pip install transformers torch --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import time

t0 = time.time()
try:
    from transformers import pipeline

    ner = pipeline(
        "ner", model="dslim/bert-base-NER", aggregation_strategy="simple"
    )
    print(f"model loaded in {time.time() - t0:.1f}s")
    DOWNLOAD_OK = True
except Exception as exc:  # noqa: BLE001 - we want the reason, whatever it is
    print("MODEL COULD NOT BE LOADED")
    print(f"{type(exc).__name__}: {exc}")
    DOWNLOAD_OK = False

# COMMAND ----------

# Real text, not a toy string. A synthetic sentence would be easier than the
# actual notes and would give an optimistic timing.
if DOWNLOAD_OK:
    pieces = (
        spark.table("healthcare_dev.silver.note_chunk")
        .join(spark.table("healthcare_dev.ops.heldout_patient"), "patient_id")
        .select("chunk_text")
        .limit(20)
        .toPandas()["chunk_text"]
        .tolist()
    )
    print(f"{len(pieces)} real pieces, average {sum(map(len, pieces)) // len(pieces)} characters")

# COMMAND ----------

if DOWNLOAD_OK:
    start = time.time()
    results = [ner(piece) for piece in pieces]
    elapsed = time.time() - start

    per_piece = elapsed / len(pieces)
    total_hours = per_piece * 41592 / 3600

    print(f"{elapsed:.1f}s for {len(pieces)} pieces")
    print(f"{per_piece:.3f}s per piece")
    print(f"--> 41,592 pieces would take {total_hours:.1f} hours")
    print()
    if total_hours > 3:
        print("TOO SLOW for the full test set. Options: fewer patients,")
        print("a smaller model, or drop stage 2 and say so in the write-up.")
    else:
        print("Workable. Stage 2 can run on the full test set.")

# COMMAND ----------

# What does it actually find? A timing with no output check is worthless —
# a model returning nothing is very fast.
if DOWNLOAD_OK:
    people = [h for r in results for h in r if h["entity_group"] == "PER"]
    places = [h for r in results for h in r if h["entity_group"] == "LOC"]
    print(f"names found: {len(people)}, places found: {len(places)}")
    print("first few names:", [h["word"] for h in people[:8]])
    if not people:
        print()
        print("NO NAMES FOUND AT ALL. The model runs but finds nothing in")
        print("these notes, which makes stage 2 pointless regardless of speed.")

# COMMAND ----------

# Hand the numbers back to whoever submitted the run. Without an explicit
# exit, printed output stays inside the notebook and the jobs API returns
# nothing — so a probe run from the command line tells you only that it
# finished, which is the least useful thing it could say.
import json  # noqa: E402

summary = {"download_ok": DOWNLOAD_OK}
if DOWNLOAD_OK:
    summary |= {
        "pieces_timed": len(pieces),
        "seconds_per_piece": round(per_piece, 3),
        "hours_for_41592_pieces": round(total_hours, 2),
        "names_found": len(people),
        "places_found": len(places),
        "sample_names": [h["word"] for h in people[:8]],
    }

dbutils.notebook.exit(json.dumps(summary))
