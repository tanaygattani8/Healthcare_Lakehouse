# Databricks notebook source
# Phase 6 drift: training vs 2020-2026, appended as one batch per run to ml.drift_report.

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

from scripts import drift
from scripts import readmission_model as rm
from scripts.readmission_story import wilson

C = "healthcare_dev"
NAN = float("nan")
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Users/tanaygattani8@gmail.com/readmission")
client = mlflow.MlflowClient()

signals = spark.table(f"{C}.gold.readmission_signals").toPandas()
train, _, prod = rm.split(signals)
rows = []


def add(check, period, subject, value, status, low=NAN, high=NAN):
    rows.append({"drift_check": check, "period": period, "subject": subject,
                 "value": float(value), "low": float(low), "high": float(high),
                 "status": status})


# Features: "all" only; "no_bypass" is a subset of it (decision P-k).
x_train, x_prod = rm.build_features(train, "all"), rm.build_features(prod, "all")
kinds = {c: "number" if c in rm.NUMBERS else "flag" if c in rm.FLAGS else "category"
         for c in x_train.columns}
for r in drift.drift_report(x_train, x_prod, kinds):
    add("feature", "2020-2026", r["feature"], r["psi"], r["status"])

for population in rm.POPULATIONS:
    name = f"{C}.ml.readmission_{population}"
    champion = client.get_model_version_by_alias(name, "champion")
    model = mlflow.sklearn.load_model(f"models:/{name}@champion")
    threshold = float(champion.tags["alert_threshold"])
    tr, pr = rm.population(train, population), rm.population(prod, population)
    # The reference is out-of-fold, as the cutoff was (D72).
    s_tr = rm.oof_scores(model, tr, population)
    s_pr = model.predict_proba(rm.build_features(pr, population))[:, 1]
    share = float((s_tr >= threshold).mean())
    years = pd.to_datetime(pr["admit_day"]).dt.year.to_numpy()
    for year in sorted(set(years)):
        part = s_pr[years == year]
        value = drift.psi(s_tr, part, "number")
        add("score", str(year), population, value, drift.status(value))
        flagged = int((part >= threshold).sum())
        add("flag_rate", str(year), population, flagged / len(part),
            drift.interval_status(share, flagged, len(part)), *wilson(flagged, len(part)))
    # Rates only, window totals only: per-year readmissions are small cells.
    k_tr, n_tr = int(tr[rm.TARGET].sum()), len(tr)
    k_pr, n_pr = int(pr[rm.TARGET].sum()), len(pr)
    add("readmission_rate", "training", population, k_tr / n_tr, "reference",
        *wilson(k_tr, n_tr))
    add("readmission_rate", "2020-2026", population, k_pr / n_pr,
        drift.interval_status(k_tr / n_tr, k_pr, n_pr), *wilson(k_pr, n_pr))

report = pd.DataFrame(rows).assign(run_at=dt.datetime.now(dt.UTC))
spark.createDataFrame(report).write.mode("append").saveAsTable(f"{C}.ml.drift_report")

with mlflow.start_run(run_name="drift"):
    mlflow.set_tags({"role": "drift"})
    mlflow.log_metrics({f"psi_{r['subject']}": r["value"] for r in rows
                        if r["drift_check"] == "feature"})
    mlflow.log_dict(report.drop(columns="run_at").to_dict("records"), "drift_report.json")

dbutils.notebook.exit(json.dumps({
    "rows": len(rows),
    "shifted": sorted({f"{r['drift_check']}:{r['subject']}:{r['period']}" for r in rows
                       if r["status"] == "shifted"}),
    "watch": sorted({f"{r['drift_check']}:{r['subject']}" for r in rows
                     if r["status"] == "watch"})}))