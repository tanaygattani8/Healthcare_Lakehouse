# Databricks notebook source
# Track B, the proof: gold's SQL tables against notebooks/gold_pyspark.py's
# PySpark ones, both directions, row for row. Every run is appended to
# ops.reconciliation_results; both only_in columns must be 0.
import contextlib
import io
import json
import time

from pyspark.sql import functions as F

C = "healthcare_dev"
PAIRS = {
    "readmission_events": (f"{C}.gold.readmission_events", f"{C}.ops.pyspark_readmission_events"),
    "patient_360": (f"{C}.gold.patient_360", f"{C}.ops.pyspark_patient_360"),
}


def plan(df):
    # Spark Connect has no handle on the JVM plan; explain() prints, so catch it.
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        df.explain(mode="formatted")
    return out.getvalue()


def timed_count(df):
    started = time.time()
    n = df.count()
    return n, time.time() - started


def columns(df):
    # Names and types only. StructType equality also compares nullability, and
    # a PySpark count() is NOT NULL where the pipeline's column is nullable.
    return [(f.name, f.dataType.simpleString()) for f in df.schema]


patients = spark.table(f"{C}.silver.patient").count()
rows, report = [], {}
for name, (sql_table, py_table) in PAIRS.items():
    # Columns the PySpark track does not build: key_copies is a gate (E59),
    # and the phase 8 stay columns are proved by readmission_signals'
    # fingerprint. drop() ignores a name a table lacks.
    a = spark.table(sql_table).drop("key_copies", "organization_id", "payer_id",
                                    "length_of_stay_days", "stay_claim_cost")
    b = spark.table(py_table)
    if columns(a) != columns(b):
        # Different columns or types make every row "different". Say which.
        report[name] = {"schema_mismatch": sorted(set(columns(a)) ^ set(columns(b)))}
        continue
    only_sql, t_sql = timed_count(a.exceptAll(b))
    only_py, t_py = timed_count(b.exceptAll(a))
    rows.append((name, patients, a.count(), b.count(), only_sql, only_py,
                 t_sql, t_py, plan(a), plan(b)))
    report[name] = {"sql_rows": rows[-1][2], "pyspark_rows": rows[-1][3],
                    "only_in_sql": only_sql, "only_in_pyspark": only_py}

if rows:
    (spark.createDataFrame(rows, "table_name string, patients long, sql_rows long, "
                                 "pyspark_rows long, only_in_sql long, only_in_pyspark long, "
                                 "sql_seconds double, pyspark_seconds double, "
                                 "sql_plan string, pyspark_plan string")
          .withColumn("run_at", F.current_timestamp())
          .select("run_at", "table_name", "patients", "sql_rows", "pyspark_rows",
                  "only_in_sql", "only_in_pyspark", "sql_seconds", "pyspark_seconds",
                  "sql_plan", "pyspark_plan")
          .write.mode("append").saveAsTable(f"{C}.ops.reconciliation_results"))

dbutils.notebook.exit(json.dumps(report))
