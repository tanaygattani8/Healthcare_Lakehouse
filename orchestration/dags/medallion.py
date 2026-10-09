"""Run the medallion pipeline end to end.

Manually triggered only. The snapshot stays a manual step after this (D36).
Nothing runs until the PHI gate passes (D81).
"""

import os

import pendulum
from airflow.providers.databricks.hooks.databricks import DatabricksHook
from airflow.providers.databricks.operators.databricks import DatabricksSubmitRunOperator
from airflow.sdk import DAG, task

CONN = "databricks_default"
# The mask policies apply to the identity the pipeline runs as (D47). Without
# a full clearance row, gold fills with '***' and fixed dates; with the wrong
# scope, gold comes out empty; neither raises an error. And a PHI column with
# no mask is the leak governance_check.sql looks for: its CHECK 1 and CHECK 3
# are copied here, and tests/test_dag_gate.py keeps the two lists in step.
PHI_GATE = """
SELECT
  (SELECT count(*) FROM healthcare_dev.ops.phi_clearance
    WHERE user_email = current_user() AND level = 'full' AND scope_state = '*') AS cleared,
  (SELECT count(*) FROM (
     SELECT DISTINCT t.schema_name, t.tag_value
     FROM healthcare_dev.information_schema.column_tags t
     LEFT JOIN healthcare_dev.information_schema.abac_policy_definitions p
            ON p.schema_name = t.schema_name AND p.policy_type = 'COLUMN_MASK'
           AND array_join(p.match_columns, ' ') LIKE concat('%''', t.tag_value, '''%')
     WHERE t.tag_name = 'phi_category' AND p.policy_name IS NULL)) AS tagged_unmasked,
  (SELECT count(*)
   FROM healthcare_dev.information_schema.columns c
   LEFT JOIN healthcare_dev.information_schema.column_tags t
          ON t.schema_name = c.table_schema AND t.table_name = c.table_name
         AND t.column_name = c.column_name AND t.tag_name = 'phi_category'
   WHERE upper(c.column_name) IN (
           'SSN', 'DRIVERS', 'PASSPORT', 'PREFIX', 'FIRST', 'MIDDLE', 'LAST', 'SUFFIX',
           'MAIDEN', 'ADDRESS', 'CITY', 'COUNTY', 'FIPS', 'BIRTHPLACE', 'ZIP', 'LAT', 'LON',
           'LATITUDE', 'LONGITUDE', 'BIRTHDATE', 'DEATHDATE', 'BIRTH_DATE', 'DEATH_DATE')
     AND c.table_schema <> 'information_schema'
     AND c.table_name NOT RLIKE
           '(br_organizations|br_providers|br_payers|dim_organization)(_[0-9]+)?$'
     AND c.table_name NOT LIKE '\\_\\_materialization\\_mat\\_%'
     AND t.column_name IS NULL) AS untagged_phi
"""

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

    @task
    def phi_gate():
        """Fail, before any compute, unless the run-as user is fully cleared
        and every PHI column is tagged and masked (D47, D79, D81)."""
        # /sql/1.0/warehouses/<id>, the same .env value scripts/dbx.py uses.
        warehouse = os.environ["DATABRICKS_HTTP_PATH"].rstrip("/").rsplit("/", 1)[1]
        reply = DatabricksHook(CONN)._do_api_call(
            ("POST", "2.0/sql/statements"),
            {"warehouse_id": warehouse, "statement": PHI_GATE, "wait_timeout": "50s",
             "on_wait_timeout": "CANCEL"})
        if reply["status"]["state"] != "SUCCEEDED":
            raise RuntimeError(f"the gate query did not finish: {reply['status']}")
        cleared, tagged_unmasked, untagged_phi = map(int, reply["result"]["data_array"][0])
        print(f"cleared={cleared} tagged_unmasked={tagged_unmasked} untagged_phi={untagged_phi}")
        if cleared != 1:
            raise RuntimeError("no full clearance row with scope '*': gold would build masked "
                               "or empty (D47)")
        if tagged_unmasked or untagged_phi:
            raise RuntimeError("a PHI column is unmasked: run sql/governance_check.sql")

    # DatabricksRunNowOperator only runs Jobs; this one submits a one-time run
    # with a pipeline task and polls it to a terminal state (D33).
    run_medallion = DatabricksSubmitRunOperator(
        task_id="run_medallion",
        databricks_conn_id=CONN,
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

    phi_gate() >> run_medallion
