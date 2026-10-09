# Databricks notebook source
# Phase 9: one retraining cursor; replay writes only to the sandbox, live may move `champion`.

# COMMAND ----------

# MAGIC %pip install -q scikit-learn==1.6.1 "mlflow[databricks]==3.16.1"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("as_of", "")
dbutils.widgets.dropdown("mode", "replay", ["replay", "live"])

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
from mlflow.models import infer_signature

from scripts import readmission_model as rm
from scripts import retrain as rt

C = "healthcare_dev"
NAME = f"{C}.ml.readmission_{rt.POPULATION}"
HISTORY = f"{C}.ml.retrain_history"
# Same trusted types as train_readmission.py (E56).
TRUSTED_TYPES = ["numpy.dtype", "sklearn.compose._column_transformer._RemainderColsList",
                 "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor"]
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Users/tanaygattani8@gmail.com/readmission")
client = mlflow.MlflowClient()

as_of = dt.date.fromisoformat(dbutils.widgets.get("as_of"))
mode = dbutils.widgets.get("mode")
assert mode in ("replay", "live"), mode

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {HISTORY} (
  as_of DATE, mode STRING, champion_version STRING, check_stays BIGINT, target DOUBLE,
  champion_rate DOUBLE, champion_low DOUBLE, champion_high DOUBLE, triggered BOOLEAN,
  cutoff_rate DOUBLE, cutoff_low DOUBLE, cutoff_high DOUBLE, cutoff_workload STRING,
  retrain_rate DOUBLE, retrain_low DOUBLE, retrain_high DOUBLE, retrain_workload STRING,
  retrain_ranking STRING, outcome STRING, new_version STRING, alias STRING,
  shifted_features STRING, mlflow_run_id STRING, written_at TIMESTAMP)
COMMENT 'Phase 9: one row per retraining cursor. Rates and verdicts only, no counts.'""")

# COMMAND ----------

# 1. The order guard, before any compute (spec §5).
history = spark.table(HISTORY).select("as_of", "mode", "alias").toPandas()
problem = rt.order_problem(as_of, mode, list(zip(history["as_of"], history["mode"],
                                                 strict=True)))
if problem:
    raise ValueError(problem)

# 2. The champion this cursor starts from (spec §2.7).
promoted = history[(history["mode"] == "replay") & history["alias"].notna()]
start_alias = ("champion" if mode == "live" or promoted.empty
               else promoted.sort_values("as_of")["alias"].iloc[-1])
champion = client.get_model_version_by_alias(NAME, start_alias)
model = mlflow.sklearn.load_model(f"models:/{NAME}@{start_alias}")
kind, params = rt.settings(champion.tags if "kind" in champion.tags
                           else client.get_run(champion.run_id).data.params)
admit_before = champion.tags.get("train_admit_before", rm.PROD_FROM)
discharged_by = champion.tags.get("labels_known_by", rm.TRAIN_UNTIL)
admit_from = champion.tags.get("train_admit_from")   # absent before D80: no lower bound

signals = rm.population(spark.table(f"{C}.gold.readmission_signals").toPandas(),
                        rt.POPULATION)
target = rt.budget(signals)
w = rt.windows(as_of)
check = signals[rt.admitted(signals, *w["check"])]
cutoff = signals[rt.admitted(signals, *w["cutoff"])]
trained = signals[rt.trained_on(signals, admit_before, discharged_by, admit_from)]
assert len(check) > 0 and len(cutoff) > 0, "an empty window"
assert check.index.intersection(trained.index).empty, "the champion trained on the check window"

# COMMAND ----------

# 3. The trigger (spec §2.3). Feature drift explains; it triggers nothing.
fresh = rm.build_pipeline(kind, params, rt.POPULATION)
champion_check = rt.window_scores(model, fresh, trained, check)
champ = rt.flag_rate(champion_check, float(champion.tags["alert_threshold"]))
triggered = not rt.on_budget(champ, target)


def r3(x):
    return round(float(x), 3)


row = {"as_of": as_of, "mode": mode, "champion_version": str(champion.version),
       "check_stays": len(check), "target": r3(target), "champion_rate": r3(champ["rate"]),
       "champion_low": r3(champ["low"]), "champion_high": r3(champ["high"]),
       "triggered": triggered,
       "shifted_features": ",".join(rt.shifted_features(trained, check)),
       "outcome": "no trigger"}

if triggered:
    # 4a. New cutoff: the same model, its cutoff re-set on the year before (spec §2.4).
    cut_threshold = rm.alert_threshold(rt.window_scores(model, fresh, trained, cutoff), target)
    cut = rt.flag_rate(champion_check, cut_threshold)
    cut_passes = rt.on_budget(cut, target)

    # 4b. Retrain on TRAIN_YEARS of stays before the window, labels known by as_of (D80).
    new_admit_before, new_discharged_by = str(w["check"][0]), str(rt.labels_known_by(as_of))
    new_admit_from = str(rt.add_years(w["check"][0], -rt.TRAIN_YEARS))
    train = signals[rt.trained_on(signals, new_admit_before, new_discharged_by,
                                  new_admit_from)]
    x_train = rm.build_features(train, rt.POPULATION)
    retrained = rm.build_pipeline(kind, params, rt.POPULATION).fit(
        x_train, train[rm.TARGET].astype(int))
    re_threshold = rm.alert_threshold(rt.window_scores(retrained, fresh, train, cutoff), target)
    retrain_check = retrained.predict_proba(rm.build_features(check, rt.POPULATION))[:, 1]
    re = rt.flag_rate(retrain_check, re_threshold)

    # 5. The gate, on the check window neither challenger has seen (spec §2.5).
    known = rt.labelled(check, as_of).to_numpy()
    ranking = rt.ranking_guard(check[rm.TARGET].to_numpy(bool)[known], retrain_check[known],
                               champion_check[known], check["patient_id"].to_numpy()[known])
    re_passes = rt.on_budget(re, target) and ranking != "clearly worse"

    row |= {"cutoff_rate": r3(cut["rate"]), "cutoff_low": r3(cut["low"]),
            "cutoff_high": r3(cut["high"]), "cutoff_workload": "pass" if cut_passes else "fail",
            "retrain_rate": r3(re["rate"]), "retrain_low": r3(re["low"]),
            "retrain_high": r3(re["high"]),
            "retrain_workload": "pass" if rt.on_budget(re, target) else "fail",
            "retrain_ranking": ranking, "outcome": rt.winner(cut_passes, re_passes)}

# COMMAND ----------

# 6. MLflow, promotion, then the history row last: a crash never leaves an unrecorded decision.
outcome = row["outcome"]
new_version = None
with mlflow.start_run(run_name=f"retrain-{mode}-{as_of}") as run:
    mlflow.set_tags({"population": rt.POPULATION, "role": "retrain_on_drift", "mode": mode,
                     "as_of": str(as_of), "outcome": outcome})
    mlflow.log_metrics({k: v for k, v in row.items()
                        if k.endswith(("_rate", "_low", "_high")) or k == "target"})
    if outcome == "retrain":
        # No input example: it would be a real stay row (phase 6 spec §4.4).
        info = mlflow.sklearn.log_model(retrained, "model",
                                        signature=infer_signature(
                                            x_train, retrained.predict_proba(x_train)),
                                        pyfunc_predict_fn="predict_proba",
                                        skops_trusted_types=TRUSTED_TYPES,
                                        registered_model_name=NAME)
        new_version = str(info.registered_model_version)
row["mlflow_run_id"] = run.info.run_id

if outcome == "new cutoff":
    new_version = str(client.copy_model_version(f"models:/{NAME}/{champion.version}",
                                                NAME).version)

if new_version:
    is_cut = outcome == "new cutoff"
    tags = {"alert_threshold": cut_threshold if is_cut else re_threshold,
            "train_admit_before": admit_before if is_cut else new_admit_before,
            "train_admit_from": admit_from if is_cut else new_admit_from,
            "labels_known_by": discharged_by if is_cut else new_discharged_by,
            "source_version": champion.version, "as_of": as_of, "mode": mode,
            "promoted_by": "retrain_on_drift", "population": rt.POPULATION,
            "beats_rule": champion.tags.get("beats_rule", "false") if is_cut else "not_judged",
            "kind": kind, **params}
    tags["prod_stays"] = int((pd.to_datetime(signals["admit_day"])
                              >= pd.Timestamp(rt.scored_from(tags))).sum())
    for key, value in tags.items():
        if value is not None:   # a pre-D80 champion has no train_admit_from; "None" is not a date
            client.set_model_version_tag(NAME, new_version, key, str(value))
    row["alias"] = f"replay_{as_of.year}" if mode == "replay" else "champion"
    client.set_registered_model_alias(NAME, row["alias"], new_version)
row["new_version"] = new_version
row["written_at"] = dt.datetime.now(dt.UTC)

schema = spark.table(HISTORY).schema
(spark.createDataFrame([tuple(row.get(f.name) for f in schema.fields)], schema)
      .write.mode("append").saveAsTable(HISTORY))

dbutils.notebook.exit(json.dumps({"outcome": outcome, "version": new_version,
                                  "alias": row.get("alias")}))
