# Databricks notebook source
# Phase 9 probes P1, P5, P6, P7 (spec §1). Kept as a record, like probe_ml.py.
# P1: does copy_model_version work on UC here, and does the copy score the same?
#     The copy is deleted at the end.
# P5: v2's flag rate per year from 2020, at its own alert_threshold (D71: 31-36%).
# P6: the last admit day in readmission_signals: the live run's as_of is the next day.
# P7: do v2's run params give back its kind and settings?

# COMMAND ----------

# MAGIC %pip install -q scikit-learn==1.6.1 "mlflow[databricks]==3.16.1"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

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

C = "healthcare_dev"
NAME = f"{C}.ml.readmission_all"
mlflow.set_registry_uri("databricks-uc")
client = mlflow.MlflowClient()
found = {}

# P6
found["p6_last_admit_day"] = str(spark.sql(
    f"SELECT max(admit_day) FROM {C}.gold.readmission_signals").first()[0])

# P7
v2 = client.get_model_version_by_alias(NAME, "champion")
params = client.get_run(v2.run_id).data.params
found["p7"] = {"version": v2.version, "kind": params.get("kind"),
               "settings": {k: params.get(k) for k in ("max_depth", "learning_rate", "C")},
               "tags": sorted(v2.tags)}

# P5: stay counts per year are in the hundreds, so they may be printed.
signals = rm.population(spark.table(f"{C}.gold.readmission_signals").toPandas(), "all")
train, _, prod = rm.split(signals)
model = mlflow.sklearn.load_model(f"models:/{NAME}@champion")
score = model.predict_proba(rm.build_features(prod, "all"))[:, 1]
flagged = score >= float(v2.tags["alert_threshold"])
year = pd.to_datetime(prod["admit_day"]).dt.year.to_numpy()
found["p5_budget"] = round(float(rm.rule_score(train).mean()), 3)
found["p5"] = {int(y): {"stays": int((year == y).sum()),
                        "flag_rate": round(float(flagged[year == y].mean()), 3)}
               for y in sorted(set(year))}

# P1
copy = client.copy_model_version(f"models:/{NAME}/{v2.version}", NAME)
copied = client.get_model_version(NAME, copy.version)
again = mlflow.sklearn.load_model(f"models:/{NAME}/{copy.version}")
found["p1"] = {"copy_version": copy.version,
               "same_scores": bool((again.predict_proba(
                   rm.build_features(prod, "all"))[:, 1] == score).all()),
               "run_id_kept": copied.run_id == v2.run_id,
               "tags_copied": sorted(copied.tags)}
client.delete_model_version(NAME, copy.version)
found["p1"]["deleted"] = True

dbutils.notebook.exit(json.dumps(found))