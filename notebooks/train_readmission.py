# Databricks notebook source
# Phase 6 training (spec §4). For each population: choose between logistic
# regression and gradient boosting by patient-grouped CV on stays from 2000 to
# 2019 (rm.TRAIN_FROM, D80), refit the winner, judge it against the rule on
# 2020-2026 twice: at the same number of alerts (D71), and at its deployed
# cutoff against the rule thinned to as many (D80). Log it all to MLflow,
# register the champion in Unity Catalog, and write ml.model_results.

# COMMAND ----------

# MAGIC %pip install -q scikit-learn==1.6.1 "mlflow[databricks]==3.16.1"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import math
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

C = "healthcare_dev"
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Users/tanaygattani8@gmail.com/readmission")
client = mlflow.MlflowClient()
# MLflow 3.16 saves sklearn models with skops, which refuses any type it is not
# told to trust (E56). These come from our own pipeline, trained in this job:
# numpy dtypes, the column transformer, and boosting's tree nodes. Stored with
# the model, so scoring and drift load it without repeating the list.
TRUSTED_TYPES = ["numpy.dtype", "sklearn.compose._column_transformer._RemainderColsList",
                 "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor"]


def metrics(row, *keys):
    # MLflow rejects nothing, but a NaN metric is noise in the comparison table.
    return {k: float(row[k]) for k in keys
            if row.get(k) is not None and not math.isnan(row[k])}


signals = spark.table(f"{C}.gold.readmission_signals").toPandas()
results, summary = [], {}

for population in rm.POPULATIONS:
    name = f"{C}.ml.readmission_{population}"
    train, gap, prod = rm.split(rm.population(signals, population))

    # 1. Choose, on training only.
    cv = rm.cv_scores(train, population)
    for row in cv:
        with mlflow.start_run(run_name=f"{population}-{row['kind']}-cv"):
            mlflow.set_tags({"population": population, "role": "candidate"})
            mlflow.log_params({"kind": row["kind"], **row["params"]})
            mlflow.log_metrics({"cv_avg_precision": row["cv_ap"],
                                "cv_avg_precision_sd": row["cv_ap_sd"]})
    best = max(cv, key=lambda r: r["cv_ap"])

    # 2. Refit the winner on every training stay; 3. fix the cutoff on
    # out-of-fold scores: in-sample ones look surer than new stays will (D72).
    x_train, y_train = rm.build_features(train, population), train[rm.TARGET].astype(int)
    pipe = rm.build_pipeline(best["kind"], best["params"], population).fit(x_train, y_train)
    train_scores = rm.oof_scores(pipe, train, population)
    threshold = rm.alert_threshold(train_scores, rm.rule_score(train).mean())

    # 4. Judge on production at the rule's alert count.
    k = int(rm.rule_score(prod).sum())
    y_prod = prod[rm.TARGET].to_numpy(bool)
    model_score = pipe.predict_proba(rm.build_features(prod, population))[:, 1]
    returning = prod["patient_id"].isin(set(train["patient_id"])).to_numpy()
    rows = rm.evaluate(y_prod, prod["patient_id"], returning, k,
                       {"rule": (rm.rule_score(prod), rm.rule_probability(train, prod)),
                        "model": (model_score, model_score)},
                       base_rate=float(y_train.mean()), name=population,
                       threshold=threshold)
    model_all = next(r for r in rows if r["scorer"] == "model" and r["patients"] == "all")
    # Spec §3.3: catches that are themselves 30-day returns (decision P-g).
    self_returns = (prod["days_since_last_discharge"] <= 30).to_numpy()
    caught_self_returns = int((rm.top_k(model_score, k) & y_prod & self_returns).sum())

    for scorer in ("base_rate", "rule"):
        row = next(r for r in rows if r["scorer"] == scorer and r["patients"] == "all")
        with mlflow.start_run(run_name=f"{population}-{scorer}"):
            mlflow.set_tags({"population": population, "role": "baseline"})
            mlflow.log_metrics(metrics(row, "recall", "avg_precision", "brier"))

    with mlflow.start_run(run_name=f"{population}-champion"):
        mlflow.set_tags({"population": population, "role": "champion"})
        mlflow.log_params({"kind": best["kind"], **best["params"], "k": k,
                           "train_stays": len(train), "gap_stays": len(gap),
                           "prod_stays": len(prod)})
        mlflow.log_metrics(metrics(model_all, "recall", "avg_precision", "brier",
                                   "diff_low", "diff_mid", "diff_high",
                                   "cut_low", "cut_mid", "cut_high")
                           | {"cv_avg_precision": best["cv_ap"],
                              "alert_threshold": threshold,
                              "caught_self_returns": caught_self_returns})
        # No input example: it would be a real stay row (spec §4.4).
        # The pyfunc flavour returns probabilities, as the signature says.
        info = mlflow.sklearn.log_model(pipe, "model",
                                        signature=infer_signature(
                                            x_train, pipe.predict_proba(x_train)),
                                        pyfunc_predict_fn="predict_proba",
                                        skops_trusted_types=TRUSTED_TYPES,
                                        registered_model_name=name)
    version = info.registered_model_version
    client.set_registered_model_alias(name, "champion", version)
    tag = {"beats": "true", "no better": "false", "too few to judge": "too_few"}
    for key, value in {"beats_rule": tag[model_all["model_verdict"]],
                       "beats_rule_at_cutoff": tag[model_all["cutoff_verdict"]],
                       "alert_threshold": threshold, "train_admit_from": rm.TRAIN_FROM,
                       "train_cutoff": rm.TRAIN_UNTIL, "population": population,
                       "kind": best["kind"], **best["params"],
                       "prod_stays": len(prod)}.items():
        client.set_model_version_tag(name, version, key, str(value))

    for row in rows:
        if row["scorer"] == "model":
            row |= {"model_kind": best["kind"], "model_version": str(version),
                    "cv_avg_precision": best["cv_ap"]}
    results += rows
    summary[population] = {
        "train_stays": len(train), "train_readmitted": int(y_train.sum()),
        "gap_stays": len(gap), "prod_stays": len(prod), "prod_readmitted": int(y_prod.sum()),
        "k": k, "champion": best["kind"], "params": best["params"],
        "cv_ap": round(best["cv_ap"], 4), "version": str(version),
        "verdict": model_all["model_verdict"],
        "diff": [round(model_all[c], 3) for c in ("diff_low", "diff_mid", "diff_high")],
        "cutoff_verdict": model_all["cutoff_verdict"],
        "cut": [round(model_all[c], 3) for c in ("cut_low", "cut_mid", "cut_high")],
        "caught_self_returns": caught_self_returns, "alert_threshold": round(threshold, 5)}

table = pd.DataFrame(results).reindex(columns=rm.RESULT_COLUMNS)
(spark.createDataFrame(table).write.mode("overwrite").option("overwriteSchema", "true")
      .saveAsTable(f"{C}.ml.model_results"))
dbutils.notebook.exit(json.dumps(summary, default=str))