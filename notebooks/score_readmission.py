# Databricks notebook source
# Batch scoring: each champion scores stays after its training; reruns replace its rows.

# COMMAND ----------

# MAGIC %pip install -q scikit-learn==1.6.1 "mlflow[databricks]==3.16.1"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import datetime as dt
import json
import os
import sys

ROOT = "/Workspace/Users/tanaygattani8@gmail.com/.bundle/healthcare-lakehouse/dev/files"
sys.path.insert(0, ROOT)
# E52: Free Edition denies MLflow direct writes to UC storage; go through the Files API.
os.environ["MLFLOW_USE_DATABRICKS_SDK_MODEL_ARTIFACTS_REPO_FOR_UC"] = "True"

import mlflow
import mlflow.sklearn
import pandas as pd

from scripts import readmission_model as rm
from scripts import retrain as rt

C = "healthcare_dev"
TABLE = f"{C}.ml.readmission_scores"
mlflow.set_registry_uri("databricks-uc")
client = mlflow.MlflowClient()

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
  patient_id STRING, stay_no BIGINT, model_name STRING, model_version STRING,
  score DOUBLE, flagged BOOLEAN, scored_at TIMESTAMP, first_encounter_id STRING)
COMMENT 'Phase 6: champion scores for 2020-2026 index stays. Labels stay in gold.'""")

signals = spark.table(f"{C}.gold.readmission_signals").toPandas()
summary = {}
for population in rm.POPULATIONS:
    name = f"{C}.ml.readmission_{population}"
    # Raises "alias champion not found" if training never registered one.
    champion = client.get_model_version_by_alias(name, "champion")
    model = mlflow.sklearn.load_model(f"models:/{name}@champion")
    # A retrained champion trained on stays after 2020; it scores only later ones.
    _, _, prod = rm.split(rm.population(signals, population),
                          prod_from=rt.scored_from(champion.tags))
    expected = int(champion.tags["prod_stays"])
    assert len(prod) == expected, f"{name}: {len(prod)} production stays, training saw {expected}"

    score = model.predict_proba(rm.build_features(prod, population))[:, 1]
    out = pd.DataFrame({
        "patient_id": prod["patient_id"].astype(str).to_numpy(),
        "stay_no": prod["stay_no"].astype("int64").to_numpy(),
        # The key to join on: stay_no is a position and can renumber (D81).
        "first_encounter_id": prod["first_encounter_id"].astype(str).to_numpy(),
        "model_name": name, "model_version": str(champion.version), "score": score,
        "flagged": score >= float(champion.tags["alert_threshold"]),
        "scored_at": dt.datetime.now(dt.UTC)})
    # mergeSchema: first_encounter_id joined the table in D81; older rows hold NULL.
    (spark.createDataFrame(out).write.mode("overwrite").option("mergeSchema", "true")
          .option("replaceWhere",
                  f"model_name = '{name}' AND model_version = '{champion.version}'")
          .saveAsTable(TABLE))
    summary[population] = {"version": str(champion.version), "rows": len(out),
                           "flagged_share": round(float(out["flagged"].mean()), 3)}

dbutils.notebook.exit(json.dumps(summary))