# Databricks notebook source
# D80 probe: what a lower bound on the training window does, before any model
# is retrained or registered. Reads gold only; logs nothing, registers nothing,
# writes nothing. For each start year and population: the training size, the
# rule's training rate (phase 9's budget), the chosen model, its cutoff, the
# production flag rate per year, age and condition drift, and the model against
# the rule two ways: at the rule's own count (D71) and at the deployed cutoff
# against the rule thinned to as many alerts (D80).

# COMMAND ----------

# MAGIC %pip install -q scikit-learn==1.6.1

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import sys

ROOT = "/Workspace/Users/tanaygattani8@gmail.com/.bundle/healthcare-lakehouse/dev/files"
sys.path.insert(0, ROOT)

import pandas as pd

from scripts import drift
from scripts import readmission_model as rm

signals = spark.table("healthcare_dev.gold.readmission_signals").toPandas()
out = []
for start in (None, "2000-01-01", "2005-01-01", "2010-01-01"):
    for population in rm.POPULATIONS:
        train, _, prod = rm.split(rm.population(signals, population), train_from=start)
        cv = rm.cv_scores(train, population)
        best = max(cv, key=lambda r: r["cv_ap"])
        pipe = rm.build_pipeline(best["kind"], best["params"], population).fit(
            rm.build_features(train, population), train[rm.TARGET].astype(int))
        budget = float(rm.rule_score(train).mean())
        threshold = rm.alert_threshold(rm.oof_scores(pipe, train, population), budget)
        score = pipe.predict_proba(rm.build_features(prod, population))[:, 1]
        y, rule = prod[rm.TARGET].to_numpy(bool), rm.rule_score(prod)
        years = pd.to_datetime(prod["admit_day"]).dt.year.to_numpy()
        equal = rm.bootstrap_difference(y, score, rule, prod["patient_id"])
        at_cut = rm.bootstrap_at_cutoff(y, score, rule, prod["patient_id"], threshold)
        out.append({
            "start": start or "all", "population": population,
            "train_stays": len(train), "train_readmitted": int(train[rm.TARGET].sum()),
            "budget": round(budget, 3), "kind": best["kind"], "params": best["params"],
            "cv_ap": round(best["cv_ap"], 4), "threshold": round(threshold, 5),
            "flag_rate": round(float((score >= threshold).mean()), 3),
            "flag_rate_by_year": {int(yr): round(float((score[years == yr] >= threshold).mean()), 3)
                                  for yr in sorted(set(years))},
            "rule_rate_prod": round(float(rule.mean()), 3),
            "psi_age": round(drift.psi(train["age_at_admit"], prod["age_at_admit"], "number"), 3),
            "psi_conditions": round(drift.psi(train["conditions_at_admit"],
                                              prod["conditions_at_admit"], "number"), 3),
            "diff_equal_count": [round(v, 3) for v in equal],
            "diff_at_cutoff": [round(v, 3) for v in at_cut],
        })
        print(out[-1])
dbutils.notebook.exit(json.dumps(out))
