# Databricks notebook source
# Phase 6 probes P1 and P2 (spec §1). Kept as a record, like p6_fhir_probe.py.
# P1: are scikit-learn and MLflow importable on serverless, at which versions,
#     and does scripts/ import from the bundle folder (decision P-a)?
# P2: does a model register in Unity Catalog, take an alias and load back?

# COMMAND ----------

# MAGIC %pip install -q scikit-learn==1.6.1 "mlflow[databricks]==3.16.1"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import contextlib
import json
import os
import platform
import sys

ROOT = "/Workspace/Users/tanaygattani8@gmail.com/.bundle/healthcare-lakehouse/dev/files"
sys.path.insert(0, ROOT)
# E52: Free Edition denies MLflow direct writes to UC storage; go through the Files API.
os.environ["MLFLOW_USE_DATABRICKS_SDK_MODEL_ARTIFACTS_REPO_FOR_UC"] = "True"

import mlflow
import mlflow.sklearn
import numpy
import pandas
import sklearn
from mlflow.models import infer_signature
from sklearn.linear_model import LogisticRegression

from scripts.readmission_story import wilson

found = {"python": platform.python_version(), "sklearn": sklearn.__version__,
         "numpy": numpy.__version__, "pandas": pandas.__version__,
         "mlflow": mlflow.__version__, "repo_import": wilson(1, 2)[1] > 0}

# P2: a four-row toy, registered, aliased, loaded back by alias, deleted.
x = pandas.DataFrame({"x": [0.0, 1.0, 2.0, 3.0]})
toy = LogisticRegression().fit(x, [0, 0, 1, 1])
mlflow.set_registry_uri("databricks-uc")
experiment = "/Users/tanaygattani8@gmail.com/probe_phase6"
mlflow.set_experiment(experiment)
name = "healthcare_dev.ml.probe_toy"
client = mlflow.MlflowClient()
try:
    with mlflow.start_run():
        info = mlflow.sklearn.log_model(
            toy, "model", signature=infer_signature(x, toy.predict_proba(x)[:, 1]),
            registered_model_name=name)
    client.set_registered_model_alias(name, "champion", info.registered_model_version)
    client.set_model_version_tag(name, info.registered_model_version, "beats_rule", "false")
    back = mlflow.sklearn.load_model(f"models:/{name}@champion")
    version = client.get_model_version_by_alias(name, "champion")
    found |= {"uc_roundtrip": bool((back.predict(x) == toy.predict(x)).all()),
              "alias_tag": version.tags.get("beats_rule")}
except Exception as error:  # report it: P2's answer is the error
    found["uc_error"] = f"{type(error).__name__}: {str(error)[:300]}"
# Also removes the half-made versions earlier failed runs left behind.
with contextlib.suppress(Exception):  # absent if registration never started
    client.delete_registered_model(name)
mlflow.delete_experiment(mlflow.get_experiment_by_name(experiment).experiment_id)

dbutils.notebook.exit(json.dumps(found))