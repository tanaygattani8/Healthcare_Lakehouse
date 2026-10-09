# Databricks notebook source
# MAGIC %md
# MAGIC # Track A — flatten FHIR bundles, and prove they agree with the CSVs
# MAGIC
# MAGIC Each bundle is one patient: `entry[]` holds every resource about them,
# MAGIC nested several levels deep. The 25 test patients only (plan D-c: all
# MAGIC 12.8 GB would hit the compute cap). **Patient resources are never
# MAGIC flattened** — they hold names and addresses, and 3a's masks do not reach
# MAGIC tables they never tagged. Encounters and conditions hold only the
# MAGIC patient id, dates and codes.

# COMMAND ----------

import json

from pyspark.sql import functions as F

# One schema per resource type: a shared inferred one turns `type` into a string (E48).
bundles = (spark.read.option("multiLine", True)
           .schema("entry ARRAY<STRUCT<resource: STRING>>")
           .json("/Volumes/healthcare_dev/bronze/landing/fhir/"))
raw = (bundles.select(F.explode("entry.resource").alias("json"))
       .withColumn("resource_type", F.get_json_object("json", "$.resourceType")))

ENCOUNTER = """id STRING, subject STRUCT<reference: STRING>,
               period STRUCT<start: STRING, `end`: STRING>, class STRUCT<code: STRING>,
               type ARRAY<STRUCT<coding: ARRAY<STRUCT<code: STRING>>>>"""
CONDITION = """id STRING, subject STRUCT<reference: STRING>,
               encounter STRUCT<reference: STRING>,
               code STRUCT<coding: ARRAY<STRUCT<code: STRING>>>,
               onsetDateTime STRING, abatementDateTime STRING"""


def parsed(resource_type, schema):
    return (raw.where(F.col("resource_type") == resource_type)
            .select(F.from_json("json", schema).alias("r")))


def ref_id(ref):
    # "urn:uuid:<id>" -> "<id>"
    return F.regexp_replace(ref, "^urn:uuid:", "")


# Visit times are instants: offsets and UTC both land on the same moment.
encounter = (parsed("Encounter", ENCOUNTER)
    .select(F.col("r.id").alias("encounter_id"),
            ref_id(F.col("r.subject.reference")).alias("patient_id"),
            F.to_timestamp("r.period.start").alias("started_at"),
            F.to_timestamp("r.period.end").alias("stopped_at"),
            F.col("r.class.code").alias("encounter_class_code"),
            F.col("r.type")[0]["coding"][0]["code"].alias("type_code")))

# Diagnosis dates are calendar dates: take them as written, not via UTC (D50).
condition = (parsed("Condition", CONDITION)
    .select(F.col("r.id").alias("condition_id"),
            ref_id(F.col("r.subject.reference")).alias("patient_id"),
            ref_id(F.col("r.encounter.reference")).alias("encounter_id"),
            F.col("r.code.coding")[0]["code"].alias("source_code"),
            F.to_date(F.substring("r.onsetDateTime", 1, 10)).alias("onset_date"),
            F.to_date(F.substring("r.abatementDateTime", 1, 10)).alias("resolved_date")))

encounter.write.mode("overwrite").saveAsTable("healthcare_dev.ops.fhir_encounter")
condition.write.mode("overwrite").saveAsTable("healthcare_dev.ops.fhir_condition")

# COMMAND ----------

# Reconcile against silver, for the same 25 patients, both directions.
ids = spark.table("healthcare_dev.ops.heldout_patient").select("patient_id")
silver_enc = (spark.table("healthcare_dev.silver.encounter").join(ids, "patient_id")
              .select("encounter_id", "patient_id", "started_at", "stopped_at"))
fhir_enc = spark.table("healthcare_dev.ops.fhir_encounter").select(silver_enc.columns)

silver_cond = (spark.table("healthcare_dev.silver.condition").join(ids, "patient_id")
               .select("patient_id", "encounter_id", "source_code", "onset_date", "resolved_date"))
fhir_cond = spark.table("healthcare_dev.ops.fhir_condition").select(silver_cond.columns)

types = raw.groupBy("resource_type").count().collect()
result = {
    "resource_types": {r.resource_type: r["count"] for r in types},
    # from_json returns NULL, not an error, when a schema does not fit. Must be 0.
    "encounters_missing_a_field": spark.table("healthcare_dev.ops.fhir_encounter")
        .where("encounter_id IS NULL OR patient_id IS NULL OR started_at IS NULL"
               " OR encounter_class_code IS NULL").count(),
    "conditions_missing_a_field": spark.table("healthcare_dev.ops.fhir_condition")
        .where("condition_id IS NULL OR patient_id IS NULL OR source_code IS NULL"
               " OR onset_date IS NULL").count(),
    "fhir_encounters": fhir_enc.count(),
    "silver_encounters": silver_enc.count(),
    "encounters_only_in_fhir": fhir_enc.exceptAll(silver_enc).count(),
    "encounters_only_in_silver": silver_enc.exceptAll(fhir_enc).count(),
    "fhir_conditions": fhir_cond.count(),
    "silver_conditions": silver_cond.count(),
    "conditions_only_in_fhir": fhir_cond.exceptAll(silver_cond).count(),
    "conditions_only_in_silver": silver_cond.exceptAll(fhir_cond).count(),
}
dbutils.notebook.exit(json.dumps(result))
