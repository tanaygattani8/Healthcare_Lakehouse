"""Run the medallion pipeline by hand, only after the PHI gate passes (D36, D81)."""

import os

import pendulum
from airflow.providers.databricks.hooks.databricks import DatabricksHook
from airflow.providers.databricks.operators.databricks import DatabricksSubmitRunOperator
from airflow.sdk import DAG, task

CONN = "databricks_default"
# governance_check.sql's CHECK 1 and 3 plus the clearance row (D47); kept in step by a test.
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
    # Never scheduled: a Free Edition quota lockout could fire unattended.
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["phase-2b"],
):

    @task
    def phi_gate():
        """Fail before any compute unless the run-as user is cleared and every PHI column masked."""
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

    # Submits a one-time run with a pipeline task; RunNow only runs Jobs (D33).
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
        # The pipeline retries itself (E19, E24).
        retries=0,
    )

    phi_gate() >> run_medallion
