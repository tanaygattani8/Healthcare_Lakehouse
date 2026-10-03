# Databricks notebook source
# Track B: readmission_events and patient_360 built a second time with the
# DataFrame API, from the rules (decision.md D58, D60), into ops, never gold.
# notebooks/reconcile_gold.py then proves the two engines agree row for row.
import json
import time

from pyspark.sql import Window
from pyspark.sql import functions as F

C = "healthcare_dev"
TZ = "America/Chicago"


def local_day(c):
    # Synthea generated everything in Chicago; silver stores UTC (D35).
    return F.to_date(F.from_utc_timestamp(c, TZ))


enc = spark.table(f"{C}.silver.encounter")
patient = spark.table(f"{C}.silver.patient")
planned = spark.table(f"{C}.gold.planned_reason")
procedure = spark.table(f"{C}.silver.procedure")
planned_procedure = spark.table(f"{C}.gold.planned_procedure")

# ---- readmission_events ------------------------------------------------------
started = time.time()
inp = (enc.where("readmission_role = 'index_eligible'")
          .select("patient_id", "encounter_id", "started_at", "stopped_at", "reason_description",
                  local_day("started_at").alias("start_day"),
                  local_day("stopped_at").alias("stop_day")))

before = (Window.partitionBy("patient_id").orderBy("started_at", "encounter_id")
                .rowsBetween(Window.unboundedPreceding, -1))
upto = (Window.partitionBy("patient_id").orderBy("started_at", "encounter_id")
              .rowsBetween(Window.unboundedPreceding, 0))

# Encounters with a procedure that is always planned: cancer treatment (D64).
planned_encounters = (procedure.join(planned_procedure.where("kind = 'cancer_treatment'"),
                                    F.col("source_code") == F.col("code"))
                               .select(F.col("encounter_id").alias("planned_encounter_id"))
                               .distinct())
inp = inp.join(planned_encounters, F.col("encounter_id") == F.col("planned_encounter_id"), "left")

# A new stay begins only if this encounter starts on a later day than every
# earlier one ended: max over all earlier rows, not just the one before.
prev_end = F.max("stop_day").over(before)
inp = inp.withColumn("starts_new_stay",
                     F.when(prev_end.isNull() | (F.col("start_day") > prev_end), 1).otherwise(0))
inp = inp.withColumn("stay_no", F.sum("starts_new_stay").over(upto))

# "First" = earliest start, then lowest id, so a tie is broken the same way
# in both engines.
first = F.struct("started_at", "encounter_id")
stays = (inp.groupBy("patient_id", "stay_no")
            .agg(F.min_by("encounter_id", first).alias("first_encounter_id"),
                 F.count("*").alias("encounters_in_stay"),
                 F.min("started_at").alias("admitted_at"),
                 F.max("stopped_at").alias("discharged_at"),
                 F.min("start_day").alias("admit_day"),
                 F.max("stop_day").alias("discharge_day"),
                 F.min_by("reason_description", first).alias("admit_reason"),
                 F.max(F.col("planned_encounter_id").isNotNull()).alias("cancer_treatment")))

# Stays with a scheduled heart operation from the day before admission to
# discharge, unless the operation was an emergency (D68).
surgery = (procedure.join(planned_procedure.where("kind like '%heart_surgery'"),
                          F.col("source_code") == F.col("code"))
                    .select(F.col("patient_id").alias("sp"),
                            local_day("started_at").alias("surgery_day"),
                            (F.col("kind") == "emergency_heart_surgery").alias("emergency")))
planned_surgery = (stays.join(surgery, (F.col("sp") == F.col("patient_id"))
                              & F.col("surgery_day").between(F.date_sub("admit_day", 1),
                                                             F.col("discharge_day")))
                        .groupBy("patient_id", "stay_no")
                        .agg((~F.max("emergency")).alias("planned_surgery"))
                        .where("planned_surgery"))

# Planned follows the reason the stay began with, except cancer treatment
# (D64) and scheduled heart surgery (D68), which are planned wherever they fall.
stays = (stays.join(planned.withColumnRenamed("reason_description", "admit_reason")
                           .withColumn("is_planned", F.lit(True)),
                    "admit_reason", "left")
              .join(planned_surgery, ["patient_id", "stay_no"], "left")
              .withColumn("is_planned",
                          F.coalesce("is_planned", F.lit(False)) | F.col("cancer_treatment")
                          | F.coalesce("planned_surgery", F.lit(False)))
              .drop("planned_surgery"))

# The data ends at the last visit of any kind, as a Chicago day.
last_day = enc.agg(local_day(F.max("started_at")).alias("last_day"))

a, b = stays.alias("a"), stays.alias("b")
unplanned_return = (
    a.join(b, (F.col("b.patient_id") == F.col("a.patient_id"))
              & (F.col("b.stay_no") > F.col("a.stay_no"))
              & ~F.col("b.is_planned")
              & F.datediff("b.admit_day", "a.discharge_day").between(1, 30))
     .groupBy(F.col("a.patient_id").alias("patient_id"), F.col("a.stay_no").alias("stay_no"))
     .agg(F.min(F.datediff("b.admit_day", "a.discharge_day")).alias("days_to_unplanned_return")))

by_stay = Window.partitionBy("patient_id").orderBy("stay_no")
days_to_next = F.datediff(F.lead("admit_day").over(by_stay), F.col("discharge_day"))

hospice = enc.where("encounter_class = 'hospice'").select(
    "patient_id", local_day("started_at").alias("hospice_day"))
to_hospice = (stays.join(hospice, "patient_id")
                   .where(F.datediff("hospice_day", "discharge_day").between(0, 1))
                   .select("patient_id", "stay_no", F.lit(True).alias("to_hospice"))
                   .distinct())

died = F.coalesce(F.col("death_date") <= F.col("discharge_day"), F.lit(False))
short = F.datediff("last_day", "discharge_day") < 30
in_hospice = F.col("to_hospice").isNotNull()
cancer = F.col("cancer_treatment")

readmission_events = (
    stays.withColumn("days_to_next_stay", days_to_next)
         .crossJoin(last_day)
         .join(patient.select("patient_id", "death_date"), "patient_id")
         .join(unplanned_return, ["patient_id", "stay_no"], "left")
         .join(to_hospice, ["patient_id", "stay_no"], "left")
         .select("patient_id", "stay_no", "first_encounter_id", "encounters_in_stay",
                 "admitted_at", "discharged_at", "admit_reason", "is_planned",
                 died.alias("excl_died_during_stay"),
                 short.alias("excl_short_followup"),
                 in_hospice.alias("excl_discharged_to_hospice"),
                 cancer.alias("excl_cancer_treatment"),
                 "days_to_next_stay",
                 "days_to_unplanned_return",
                 F.col("days_to_unplanned_return").isNotNull().alias("readmitted_30d"),
                 (~(died | short | in_hospice | cancer)).alias("is_index_stay")))

# overwriteSchema: rebuilt whole every run, so a rule that adds a column
# (D64's excl_cancer_treatment) replaces the old schema instead of failing.
(readmission_events.write.mode("overwrite").option("overwriteSchema", "true")
                   .saveAsTable(f"{C}.ops.pyspark_readmission_events"))
seconds_readmission = time.time() - started

# ---- patient_360 --------------------------------------------------------------
started = time.time()
fact = spark.table(f"{C}.gold.fact_encounter")
condition = spark.table(f"{C}.silver.condition")
measure_code = spark.table(f"{C}.gold.measure_code")

data_end = enc.agg(F.to_date(F.max("started_at")).alias("last_day"))

# From fact_encounter, not silver: money is already DECIMAL(14,2).
visits = fact.groupBy("patient_id").agg(
    F.count("*").alias("encounters"),
    F.count_if(F.col("encounter_class") == "inpatient").alias("inpatient_encounters"),
    F.count_if(F.col("encounter_class") == "emergency").alias("emergency_encounters"),
    F.count_if(F.col("canonical_class") == "ambulatory").alias("ambulatory_encounters"),
    F.count_if(F.col("canonical_class") == "preventive").alias("preventive_encounters"),
    F.sum("total_claim_cost").alias("total_claim_cost"),
    F.max("started_at").alias("last_visit_at"))

conditions = condition.groupBy("patient_id").agg(
    F.count("*").alias("conditions"),
    F.count_if(F.col("resolved_date").isNull()).alias("active_conditions"))

# Latest value of each vital: only that code's rows count, then the value at
# the latest moment.
LATEST = {"39156-5": "latest_bmi", "8480-6": "latest_systolic",
          "8462-4": "latest_diastolic", "4548-4": "latest_hba1c"}
latest = (spark.table(f"{C}.silver.observation")
               .where(F.col("source_code").isin(list(LATEST)))
               .groupBy("patient_id")
               .agg(*[F.max_by(F.when(F.col("source_code") == code, F.col("value_number")),
                               F.when(F.col("source_code") == code, F.col("observed_at")))
                       .alias(name) for code, name in LATEST.items()]))

denominator = measure_code.where("role = 'denominator' AND source = 'condition'")
flags = (condition.where(F.col("resolved_date").isNull())
                  .join(denominator, denominator.code == condition.source_code)
                  .groupBy("patient_id")
                  .agg(F.max(F.col("measure") == "diabetes_hba1c").alias("has_diabetes"),
                       F.max(F.col("measure") == "bp_control").alias("has_hypertension"),
                       F.max(F.col("measure") == "statin_therapy")
                        .alias("has_cardiovascular_disease")))

readmits = (spark.table(f"{C}.ops.pyspark_readmission_events").groupBy("patient_id")
                 .agg(F.count_if("is_index_stay").alias("index_stays"),
                      F.count_if(F.col("is_index_stay") & F.col("readmitted_30d"))
                       .alias("readmissions_30d")))

# Safe Harbor: ages over 89 are grouped. 90 means "90 or older".
age = F.least(F.floor(F.months_between(F.coalesce("death_date", "last_day"), "birth_date") / 12),
              F.lit(90))

patient_360 = (
    patient.crossJoin(data_end)
           .join(visits, "patient_id", "left")
           .join(conditions, "patient_id", "left")
           .join(latest, "patient_id", "left")
           .join(flags, "patient_id", "left")
           .join(readmits, "patient_id", "left")
           .select("patient_id",
                   F.col("GENDER").alias("gender"),
                   F.col("RACE").alias("race"),
                   F.col("ETHNICITY").alias("ethnicity"),
                   F.col("MARITAL").alias("marital"),
                   "is_deceased",
                   age.alias("age_years"),
                   *[F.coalesce(c, F.lit(0)).alias(c) for c in (
                       "encounters", "inpatient_encounters", "emergency_encounters",
                       "ambulatory_encounters", "preventive_encounters", "total_claim_cost")],
                   "last_visit_at",
                   F.coalesce("conditions", F.lit(0)).alias("conditions"),
                   F.coalesce("active_conditions", F.lit(0)).alias("active_conditions"),
                   F.round("latest_bmi", 1).alias("latest_bmi"),
                   F.round("latest_systolic", 0).alias("latest_systolic"),
                   F.round("latest_diastolic", 0).alias("latest_diastolic"),
                   F.round("latest_hba1c", 1).alias("latest_hba1c"),
                   *[F.coalesce(c, F.lit(False)).alias(c) for c in (
                       "has_diabetes", "has_hypertension", "has_cardiovascular_disease")],
                   F.coalesce("index_stays", F.lit(0)).alias("index_stays"),
                   F.coalesce("readmissions_30d", F.lit(0)).alias("readmissions_30d")))

patient_360.write.mode("overwrite").saveAsTable(f"{C}.ops.pyspark_patient_360")
seconds_patient_360 = time.time() - started

dbutils.notebook.exit(json.dumps({
    "seconds_readmission_events": round(seconds_readmission, 1),
    "seconds_patient_360": round(seconds_patient_360, 1),
    "session_time_zone": spark.conf.get("spark.sql.session.timeZone"),
}))
