-- One row per patient, everything about them in one place. No names,
-- addresses or identifier numbers, and no income or spend (near-unique per
-- person, D56). Age is capped at 90: Safe Harbor groups every age over 89.

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.patient_360 (
    -- Safe Harbor: every age over 89 is grouped, so 90 is the ceiling.
    CONSTRAINT age_known_and_capped EXPECT (age_years IS NOT NULL AND age_years <= 90) ON VIOLATION FAIL UPDATE
)
COMMENT "One row per patient. No names, addresses or identifier numbers; age capped at 90."
TBLPROPERTIES ("quality" = "gold")
AS
WITH data_end AS (
    SELECT to_date(max(started_at)) AS last_day FROM ${catalog}.silver.encounter
),
-- From fact_encounter, not silver: its money is already DECIMAL, so these
-- totals equal the fact table's in any engine.
visits AS (
    SELECT patient_id,
           count(*)                                    AS encounters,
           count_if(encounter_class = 'inpatient')     AS inpatient_encounters,
           count_if(encounter_class = 'emergency')     AS emergency_encounters,
           count_if(canonical_class = 'ambulatory')    AS ambulatory_encounters,
           count_if(canonical_class = 'preventive')    AS preventive_encounters,
           sum(total_claim_cost)                       AS total_claim_cost,
           max(started_at)                             AS last_visit_at
    FROM ${catalog}.gold.fact_encounter GROUP BY patient_id
),
conditions AS (
    SELECT patient_id,
           count(*)                              AS conditions,
           count_if(resolved_date IS NULL)       AS active_conditions
    FROM ${catalog}.silver.condition GROUP BY patient_id
),
latest AS (
    SELECT patient_id,
           max_by(value_number, observed_at) FILTER (WHERE source_code = '39156-5') AS latest_bmi,
           max_by(value_number, observed_at) FILTER (WHERE source_code = '8480-6')  AS latest_systolic,
           max_by(value_number, observed_at) FILTER (WHERE source_code = '8462-4')  AS latest_diastolic,
           max_by(value_number, observed_at) FILTER (WHERE source_code = '4548-4')  AS latest_hba1c
    FROM ${catalog}.silver.observation
    WHERE source_code IN ('39156-5', '8480-6', '8462-4', '4548-4')
    GROUP BY patient_id
),
-- Conditions still open today, by the same code lists the care gaps use.
flags AS (
    SELECT c.patient_id,
           max(mc.measure = 'diabetes_hba1c') AS has_diabetes,
           max(mc.measure = 'bp_control')     AS has_hypertension,
           max(mc.measure = 'statin_therapy') AS has_cardiovascular_disease
    FROM ${catalog}.silver.condition c
    JOIN ${catalog}.gold.measure_code mc
      ON mc.role = 'denominator' AND mc.source = 'condition' AND mc.code = c.source_code
    WHERE c.resolved_date IS NULL
    GROUP BY c.patient_id
),
readmits AS (
    SELECT patient_id,
           count_if(is_index_stay)                    AS index_stays,
           count_if(is_index_stay AND readmitted_30d) AS readmissions_30d
    FROM ${catalog}.gold.readmission_events GROUP BY patient_id
)
SELECT p.patient_id,
       p.GENDER    AS gender,
       p.RACE      AS race,
       p.ETHNICITY AS ethnicity,
       p.MARITAL   AS marital,
       p.is_deceased,
       -- 90 means "90 or older".
       least(floor(months_between(coalesce(p.death_date, d.last_day), p.birth_date) / 12), 90)
                                                    AS age_years,
       coalesce(v.encounters, 0)                    AS encounters,
       coalesce(v.inpatient_encounters, 0)          AS inpatient_encounters,
       coalesce(v.emergency_encounters, 0)          AS emergency_encounters,
       coalesce(v.ambulatory_encounters, 0)         AS ambulatory_encounters,
       coalesce(v.preventive_encounters, 0)         AS preventive_encounters,
       coalesce(v.total_claim_cost, 0)              AS total_claim_cost,
       v.last_visit_at,
       coalesce(c.conditions, 0)                    AS conditions,
       coalesce(c.active_conditions, 0)             AS active_conditions,
       round(l.latest_bmi, 1)                       AS latest_bmi,
       round(l.latest_systolic, 0)                  AS latest_systolic,
       round(l.latest_diastolic, 0)                 AS latest_diastolic,
       round(l.latest_hba1c, 1)                     AS latest_hba1c,
       coalesce(f.has_diabetes, false)              AS has_diabetes,
       coalesce(f.has_hypertension, false)          AS has_hypertension,
       coalesce(f.has_cardiovascular_disease, false) AS has_cardiovascular_disease,
       coalesce(r.index_stays, 0)                   AS index_stays,
       coalesce(r.readmissions_30d, 0)              AS readmissions_30d
FROM ${catalog}.silver.patient p
CROSS JOIN data_end d
LEFT JOIN visits v     ON v.patient_id = p.patient_id
LEFT JOIN conditions c ON c.patient_id = p.patient_id
LEFT JOIN latest l     ON l.patient_id = p.patient_id
LEFT JOIN flags f      ON f.patient_id = p.patient_id
LEFT JOIN readmits r   ON r.patient_id = p.patient_id;
