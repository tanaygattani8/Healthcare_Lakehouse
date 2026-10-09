# Databricks notebook source
# Phase 4 probe P6: do FHIR bundles parse, and do their encounter ids match
# silver's? One bundle only. Answered 2026-09-27: 14 of 14 (decision.md D57).
import json

from pyspark.sql import functions as F

raw = (spark.read.option("multiLine", True)
       .json("/Volumes/healthcare_dev/bronze/landing/fhir_probe/"))
entries = raw.select(F.explode("entry").alias("e")).select("e.resource.*")
by_type = {r.resourceType: r["count"] for r in entries.groupBy("resourceType").count().collect()}

enc = entries.where("resourceType = 'Encounter'").select("id")
match = enc.join(spark.table("healthcare_dev.silver.encounter")
                 .select(F.col("encounter_id").alias("id")), "id").count()

dbutils.notebook.exit(json.dumps({
    "resource_types": by_type,
    "fhir_encounters": enc.count(),
    "found_in_silver_by_id": match,
}))
