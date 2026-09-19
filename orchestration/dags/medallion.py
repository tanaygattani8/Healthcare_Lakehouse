"""Run the medallion pipeline end to end.

Manually triggered only. The snapshot stays a manual step after this (D36).
"""

import os

import pendulum
from airflow.providers.databricks.operators.databricks import DatabricksSubmitRunOperator
from airflow.sdk import DAG

with DAG(
    dag_id="medallion",
    # Never scheduled. On Databricks Free Edition, quota exhaustion locks
    # workspace compute for the rest of the day; a DAG firing on a timer can
    # do that while nobody is watching. Runs only when triggered by hand.
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["phase-2b"],
):
    # DatabricksRunNowOperator only runs Jobs; this one submits a one-time run
    # with a pipeline task and polls it to a terminal state (D33).
    DatabricksSubmitRunOperator(
        task_id="run_medallion",
        databricks_conn_id="databricks_default",
        run_name="airflow-medallion",
        tasks=[
            {
                "task_key": "medallion",
                "pipeline_task": {"pipeline_id": os.environ["MEDALLION_PIPELINE_ID"]},
            }
        ],
        # The pipeline already retries itself on failure (errors.md E19,
        # E24). Retrying here too turns one failure into several runs.
        retries=0,
    )
