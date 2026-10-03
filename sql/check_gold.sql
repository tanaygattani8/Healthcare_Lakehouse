-- Checks for the gold layer. Grows with each phase 4 step; rerun it whole.

-- Step 1. Every one of these must be 0.
SELECT count_if(o.organization_id IS NULL) AS encounters_with_unknown_organization,
       count_if(p.provider_id IS NULL)     AS encounters_with_unknown_provider,
       count_if(y.payer_id IS NULL)        AS encounters_with_unknown_payer
FROM healthcare_dev.silver.encounter e
LEFT JOIN healthcare_dev.gold.dim_organization o ON o.organization_id = e.organization_id
LEFT JOIN healthcare_dev.gold.dim_provider     p ON p.provider_id     = e.provider_id
LEFT JOIN healthcare_dev.gold.dim_payer        y ON y.payer_id        = e.payer_id;

-- Each reference table has one row per id. Must be 0.
SELECT (SELECT count(*) - count(DISTINCT organization_id) FROM healthcare_dev.gold.dim_organization) AS duplicate_organizations,
       (SELECT count(*) - count(DISTINCT provider_id) FROM healthcare_dev.gold.dim_provider)         AS duplicate_providers,
       (SELECT count(*) - count(DISTINCT payer_id) FROM healthcare_dev.gold.dim_payer)               AS duplicate_payers;

SELECT min(calendar_date), max(calendar_date), count(*) AS days,
       count(*) - count(DISTINCT date_key) AS duplicate_days_must_be_0
FROM healthcare_dev.gold.dim_date;

-- Step 2. Same rows as silver, and the money adds up the same. The two
-- totals may differ by cents (round-then-add vs add-then-round); a dollar is a bug.
SELECT (SELECT count(*) FROM healthcare_dev.gold.fact_encounter)   AS gold_rows,
       (SELECT count(*) FROM healthcare_dev.silver.encounter)      AS silver_rows,
       (SELECT sum(total_claim_cost) FROM healthcare_dev.gold.fact_encounter)  AS gold_total,
       (SELECT round(sum(total_claim_cost), 2) FROM healthcare_dev.silver.encounter) AS silver_total,
       (SELECT count_if(duration_hours < 0) FROM healthcare_dev.gold.fact_encounter)
                                                                    AS negative_durations_must_be_0;

-- Every visit's dates exist in dim_date, and no insurer paid more than the
-- bill (patient_paid is total minus coverage, so that shows as negative). Must be 0.
SELECT count_if(ds.date_key IS NULL)                                   AS start_not_in_dim_date,
       count_if(f.stop_date_key IS NOT NULL AND dt.date_key IS NULL)   AS stop_not_in_dim_date,
       count_if(f.patient_paid < 0)                                    AS coverage_above_bill
FROM healthcare_dev.gold.fact_encounter f
LEFT JOIN healthcare_dev.gold.dim_date ds ON ds.date_key = f.start_date_key
LEFT JOIN healthcare_dev.gold.dim_date dt ON dt.date_key = f.stop_date_key;

-- Step 3, check B. The gate's own rules, on silver: one row per ENCOUNTER,
-- UTC days, data ending at the last hospital discharge. Must equal the gate
-- (1,292 / 24 / 3 / 1,265 / 202 on 2026-09-27), or differ only by the
-- hospital encounters silver quarantined, counted below.
WITH inp AS (
    SELECT patient_id, started_at AS admitted, stopped_at AS discharged,
           lead(started_at) OVER (PARTITION BY patient_id ORDER BY started_at) AS next_admitted
    FROM healthcare_dev.silver.encounter WHERE encounter_class = 'inpatient'
),
b AS (SELECT max(discharged) AS data_end FROM inp),
f AS (
    SELECT i.*,
           coalesce(p.death_date <= to_date(i.discharged), false) AS died,
           datediff(b.data_end, i.discharged) < 30                AS short,
           i.next_admitted IS NOT NULL
             AND datediff(i.next_admitted, i.discharged) BETWEEN 1 AND 30 AS readmitted
    FROM inp i CROSS JOIN b
    JOIN healthcare_dev.silver.patient p USING (patient_id)
)
SELECT count(*) AS inpatient_encounters,
       count_if(died) AS excluded_death,
       count_if(short AND NOT died) AS excluded_short_followup,
       count_if(NOT died AND NOT short) AS index_admissions,
       count_if(NOT died AND NOT short AND readmitted) AS readmissions
FROM f;

SELECT count(*) AS inpatient_encounters_quarantined
FROM healthcare_dev.ops.quarantine_encounter WHERE encounter_class = 'inpatient';

-- Step 3, check C. The real table: rate and every exclusion.
SELECT count(*)                                         AS stays,
       sum(encounters_in_stay) - count(*)               AS encounters_merged_away,
       count_if(excl_died_during_stay)                  AS excl_died,
       count_if(excl_short_followup)                    AS excl_short_followup,
       count_if(excl_discharged_to_hospice)             AS excl_hospice,
       count_if(excl_cancer_treatment)                  AS excl_cancer_treatment,
       count_if(is_index_stay IS NULL)                  AS index_unknown_must_be_0,
       count_if(is_index_stay)                          AS index_stays,
       count_if(is_index_stay AND readmitted_30d)       AS readmitted,
       round(100 * count_if(is_index_stay AND readmitted_30d)
             / count_if(is_index_stay), 2)              AS readmission_rate_pct,
       count_if(is_index_stay AND days_to_next_stay BETWEEN 1 AND 30
                AND NOT readmitted_30d)                 AS returns_not_counted_planned
FROM healthcare_dev.gold.readmission_events;

-- Step 3, check D. The patient with the most merged encounters, stay by stay.
-- Compare by hand with their raw inpatient encounters in silver.encounter.
SELECT stay_no, encounters_in_stay, admitted_at, discharged_at,
       days_to_next_stay, readmitted_30d
FROM healthcare_dev.gold.readmission_events
WHERE patient_id = (SELECT max_by(patient_id, encounters_in_stay)
                    FROM healthcare_dev.gold.readmission_events)
ORDER BY stay_no;

-- Step 4. One line per measure. Every column is a count except the rate.
SELECT measure, measure_year,
       count(*)                                              AS in_denominator,
       count_if(excl_age)                                    AS excl_age,
       count_if(excl_died)                                   AS excl_died,
       count_if(excl_hospice)                                AS excl_hospice,
       count_if(NOT (excl_age OR excl_died OR excl_hospice)) AS eligible,
       count_if(numerator_met AND NOT (excl_age OR excl_died OR excl_hospice)) AS met,
       count_if(gap)                                         AS gaps,
       round(100 * count_if(numerator_met AND NOT (excl_age OR excl_died OR excl_hospice))
             / count_if(NOT (excl_age OR excl_died OR excl_hospice)), 1) AS met_pct
FROM healthcare_dev.gold.care_gap
GROUP BY measure, measure_year ORDER BY measure;

-- The statin rule, both ways. Nystatin counted: must be 0 (none in this
-- data, so this cannot fail here, D57). A 'statin' medication the rule
-- misses: must be 0, and this one can fail - a brand not in measure_code.
SELECT count_if(lower(m.source_description) LIKE '%nystatin%' AND hit.code IS NOT NULL)
                                                        AS nystatin_counted_must_be_0,
       count_if(lower(m.source_description) NOT LIKE '%nystatin%' AND hit.code IS NULL)
                                                        AS statin_missed_must_be_0,
       count_if(hit.code IS NOT NULL)                   AS statin_rows_matched
FROM healthcare_dev.silver.medication m
LEFT JOIN healthcare_dev.gold.measure_code hit
  ON hit.measure = 'statin_therapy' AND hit.role = 'numerator'
 AND lower(m.source_description) RLIKE concat('\\b', hit.code, '\\b')
WHERE lower(m.source_description) LIKE '%statin%';

-- Step 5. One row per patient, and it adds up to the other gold tables.
-- rows = patients = silver_patients = 1,148; encounters_total = fact_rows;
-- cost_total = fact_cost; readmissions_total = readmission_rows; oldest <= 90.
SELECT count(*) AS rows, count(DISTINCT patient_id) AS patients,
       (SELECT count(*) FROM healthcare_dev.silver.patient) AS silver_patients,
       sum(encounters) AS encounters_total,
       (SELECT count(*) FROM healthcare_dev.gold.fact_encounter) AS fact_rows,
       sum(total_claim_cost) AS cost_total,
       (SELECT sum(total_claim_cost) FROM healthcare_dev.gold.fact_encounter) AS fact_cost,
       sum(readmissions_30d) AS readmissions_total,
       (SELECT count_if(is_index_stay AND readmitted_30d)
          FROM healthcare_dev.gold.readmission_events) AS readmission_rows,
       max(age_years) AS oldest_must_be_90_or_less,
       count_if(age_years IS NULL) AS age_unknown_must_be_0
FROM healthcare_dev.gold.patient_360;

-- Gold must carry no governed tag: nothing in it is a direct identifier. Must be empty.
SELECT table_name, column_name, tag_name, tag_value
FROM healthcare_dev.information_schema.column_tags
WHERE schema_name = 'gold';

-- Phase 5. readmission_signals: one row per index stay, agreeing with
-- readmission_events. Expect rows = keys = 10724, readmitted = 140 (D68), and 0 in
-- every *_must_be_0 column.
SELECT count(*)                                                    AS rows,
       count(DISTINCT patient_id, stay_no)                         AS keys,
       count_if(outcome_readmitted_30d)                            AS readmitted,
       count_if(outcome_readmitted_30d <> (outcome_return_stay_cost IS NOT NULL))
                                                                   AS return_cost_mismatch_must_be_0,
       count_if(post_followup_7d AND outcome_days_to_return = 1)   AS followup_after_return_must_be_0,
       count_if(age_at_admit IS NULL OR age_at_admit > 90)         AS age_bad_must_be_0,
       count_if(stay_claim_cost IS NULL)                           AS cost_missing_must_be_0
FROM healthcare_dev.gold.readmission_signals;

-- What the story splits on. Six rows: five names and "other". Copy the five
-- names into Task 10 (the snapshot guard).
SELECT admit_reason_group, count(*) AS index_stays,
       count_if(outcome_readmitted_30d) AS readmitted
FROM healthcare_dev.gold.readmission_signals
GROUP BY ALL ORDER BY index_stays DESC;

-- The two medians, and how many stays sit on each side of them.
SELECT median(conditions_at_admit) AS conditions_median,
       count_if(above_median_conditions) AS above_conditions,
       median(length_of_stay_days) AS length_of_stay_median,
       count_if(above_median_length_of_stay) AS above_length_of_stay,
       count_if(post_followup_7d) AS followed_up_7d,
       count_if(prior_stays_12m >= 1) AS had_prior_stay
FROM healthcare_dev.gold.readmission_signals;
