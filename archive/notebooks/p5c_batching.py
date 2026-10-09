# Databricks notebook source
# MAGIC %md
# MAGIC # P5c — does batching make the right model affordable?
# MAGIC
# MAGIC P5b: `obi/deid_roberta_i2b2` finds the patient's real name 20 times out
# MAGIC of 20, and takes 4.16s per piece — 48 hours for the 41,592-piece test
# MAGIC set. Correct but unaffordable.
# MAGIC
# MAGIC That timing came from a Python loop, one piece at a time. Transformers
# MAGIC batches on CPU, which is normally 2-4x faster. If batching gets this
# MAGIC under about 6 hours the test set stays at 200 patients. If not, the
# MAGIC test set has to shrink and that becomes a documented limitation.

# COMMAND ----------

# MAGIC %pip install transformers torch --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import time

import torch
from transformers import pipeline

print(f"threads available: {torch.get_num_threads()}")

pieces = (
    spark.table("healthcare_dev.silver.note_chunk")
    .join(spark.table("healthcare_dev.ops.heldout_patient"), "patient_id")
    .select("chunk_text")
    .limit(64)
    .toPandas()["chunk_text"]
    .tolist()
)
print(f"{len(pieces)} pieces")

# COMMAND ----------

results = {}

for batch_size in (1, 8, 32):
    ner = pipeline(
        "ner",
        model="obi/deid_roberta_i2b2",
        aggregation_strategy="simple",
        batch_size=batch_size,
    )
    start = time.time()
    _ = ner(pieces)
    elapsed = time.time() - start
    per_piece = elapsed / len(pieces)
    results[f"batch_{batch_size}"] = {
        "seconds_per_piece": round(per_piece, 3),
        "hours_for_41592": round(per_piece * 41592 / 3600, 2),
    }
    print(f"batch_size={batch_size}: {per_piece:.3f}s/piece, "
          f"{per_piece * 41592 / 3600:.1f}h for the test set")

# COMMAND ----------

best = min(results.values(), key=lambda r: r["hours_for_41592"])
results["verdict"] = (
    "test set stays at 200 patients" if best["hours_for_41592"] <= 6
    else f"still {best['hours_for_41592']}h — the test set has to shrink"
)
print(results["verdict"])

dbutils.notebook.exit(json.dumps(results))
