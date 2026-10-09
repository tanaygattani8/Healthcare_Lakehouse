-- Phase 4 step 8: run once; reconcile_gold.py appends per table per run.
CREATE TABLE IF NOT EXISTS healthcare_dev.ops.reconciliation_results (
    run_at            TIMESTAMP,
    table_name        STRING,
    patients          BIGINT,
    sql_rows          BIGINT,
    pyspark_rows      BIGINT,
    only_in_sql       BIGINT,
    only_in_pyspark   BIGINT,
    sql_seconds       DOUBLE,
    pyspark_seconds   DOUBLE,
    sql_plan          STRING,
    pyspark_plan      STRING
)
COMMENT "Every SQL-vs-PySpark reconciliation run. Both only_in columns must be 0.";
