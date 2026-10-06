"""Retraining on drift, one cursor per run (phase 9, spec §3.4).

Manually triggered only, like medallion: one run per yearly cursor, with
`as_of` and `mode` in the trigger. Nothing trains until gold has passed its
gates (D73). The snapshot stays a manual step (D36).
"""

import json
import os

import pendulum
from airflow.providers.databricks.hooks.databricks import DatabricksHook
from airflow.providers.databricks.operators.databricks import DatabricksSubmitRunOperator
from airflow.sdk import DAG, Param, task

CONN = "databricks_default"
PIPELINE = os.environ["MEDALLION_PIPELINE_ID"]
NOTEBOOKS = ("/Workspace/Users/tanaygattani8@gmail.com/.bundle/"
             "healthcare-lakehouse/dev/files/notebooks")
API = "2.0"   # probe P2: the hook adds "api/" itself
JOBS = "2.1"  # probe P3
FINISHED = {"COMPLETED", "FAILED", "CANCELED"}

with DAG(
    dag_id="retrain",
    # Never scheduled, for the same reason as medallion: a quota lockout
    # while nobody is watching. One run per cursor, in order, by hand.
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    # Each cursor starts from the champion the previous one left.
    max_active_runs=1,
    params={"as_of": Param(type="string", format="date",
                           description="Today, as the cursor sees it: 2021-01-01 to 2026-01-01"),
            "mode": Param("replay", enum=["replay", "live"])},
    # The notebook's own guards make a blind retry pointless, and quota makes it costly.
    default_args={"retries": 0},
    tags=["phase-9"],
):

    @task
    def gold_is_gated():
        """Fail unless no pipeline update is running and the latest real one
        (not validate-only) COMPLETED. A failed gate fails its update, so
        COMPLETED means gold passed its gates (D73)."""
        updates = DatabricksHook(CONN)._do_api_call(
            ("GET", f"{API}/pipelines/{PIPELINE}/updates"), {"max_results": 25})["updates"]
        running = [u for u in updates if u["state"] not in FINISHED]
        if running:
            raise RuntimeError(f"update {running[0]['update_id']} is {running[0]['state']}")
        real = [u for u in updates if not u.get("validate_only")]
        if not real or real[0]["state"] != "COMPLETED":
            raise RuntimeError(f"the latest update did not complete: {real[:1]}")
        print("gold passed its gates in update", real[0]["update_id"])

    retrain = DatabricksSubmitRunOperator(
        task_id="retrain",
        databricks_conn_id=CONN,
        run_name="airflow-retrain-{{ params.mode }}-{{ params.as_of }}",
        tasks=[{"task_key": "retrain",
                "notebook_task": {"notebook_path": f"{NOTEBOOKS}/retrain_readmission",
                                  "base_parameters": {"as_of": "{{ params.as_of }}",
                                                      "mode": "{{ params.mode }}"}}}],
    )

    @task.short_circuit
    def promoted_live(params=None, ti=None) -> bool:
        """Log the cursor's outcome; go on to rescore only for a live promotion."""
        hook = DatabricksHook(CONN)
        run = hook._do_api_call(("GET", f"{JOBS}/jobs/runs/get"),
                                {"run_id": ti.xcom_pull(task_ids="retrain", key="run_id")})
        output = hook._do_api_call(("GET", f"{JOBS}/jobs/runs/get-output"),
                                   {"run_id": run["tasks"][0]["run_id"]})
        result = json.loads(output["notebook_output"]["result"])
        print("as_of", params["as_of"], params["mode"], "->", result)
        return params["mode"] == "live" and result["outcome"] in ("new cutoff", "retrain")

    rescore = DatabricksSubmitRunOperator(
        task_id="rescore",
        databricks_conn_id=CONN,
        run_name="airflow-rescore",
        tasks=[{"task_key": "rescore",
                "notebook_task": {"notebook_path": f"{NOTEBOOKS}/score_readmission"}}],
    )

    gold_is_gated() >> retrain >> promoted_live() >> rescore
