-- The contract (D73): declared types fail a retype at build; NULL-safe row gates (E57).
-- Keep each CONSTRAINT on one line: tests/test_gold_contract.py reads them line by line.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.readmission_signals (
    patient_id STRING,
    stay_no BIGINT,
    first_encounter_id STRING,
    admit_year INT,
    age_at_admit BIGINT,
    age_band STRING,
    gender STRING,
    has_diabetes BOOLEAN,
    has_hypertension BOOLEAN,
    has_cardiovascular_disease BOOLEAN,
    conditions_at_admit BIGINT,
    above_median_conditions BOOLEAN,
    admit_reason STRING,
    admit_reason_group STRING,
    is_planned BOOLEAN,
    length_of_stay_days INT,
    above_median_length_of_stay BOOLEAN,
    prior_stays_12m BIGINT,
    prior_emergency_12m BIGINT,
    encounters_in_stay BIGINT,
    days_since_last_discharge INT,
    had_bypass_surgery BOOLEAN,
    arrived_via_emergency BOOLEAN,
    admit_day DATE,
    discharge_day DATE,
    stay_claim_cost DECIMAL(24,2),
    post_followup_7d BOOLEAN,
    outcome_readmitted_30d BOOLEAN,
    outcome_days_to_return INT,
    outcome_return_stay_cost DECIMAL(24,2),
    key_copies BIGINT,
    -- A duplicated stay fails here, before the table is replaced (E59).
    CONSTRAINT one_row_per_stay EXPECT (key_copies = 1) ON VIOLATION FAIL UPDATE,
    CONSTRAINT age_known_and_capped EXPECT (age_at_admit IS NOT NULL AND age_at_admit <= 90) ON VIOLATION FAIL UPDATE,
    CONSTRAINT cost_present EXPECT (stay_claim_cost IS NOT NULL) ON VIOLATION FAIL UPDATE,
    CONSTRAINT return_cost_iff_readmitted EXPECT (outcome_readmitted_30d = (outcome_return_stay_cost IS NOT NULL)) ON VIOLATION FAIL UPDATE,
    CONSTRAINT no_followup_after_return EXPECT (NOT (post_followup_7d AND outcome_days_to_return <=> 1)) ON VIOLATION FAIL UPDATE,
    CONSTRAINT no_overlapping_stay EXPECT (days_since_last_discharge IS NULL OR days_since_last_discharge >= 1) ON VIOLATION FAIL UPDATE,
    CONSTRAINT has_an_encounter EXPECT (encounters_in_stay >= 1) ON VIOLATION FAIL UPDATE,
    CONSTRAINT admit_not_after_discharge EXPECT (admit_day <= discharge_day) ON VIOLATION FAIL UPDATE,
    CONSTRAINT year_matches_day EXPECT (admit_year = year(admit_day)) ON VIOLATION FAIL UPDATE
)
COMMENT "One row per index stay. Never model features: post_* (known only after discharge), outcome_* (the answer), stay_claim_cost (the bill is not final at discharge), admit_year, admit_day and discharge_day (the phase 6 split), the keys patient_id, stay_no, first_encounter_id, and key_copies (a gate)."
TBLPROPERTIES ("quality" = "gold")
AS
WITH stays AS (
    SELECT *,
           to_date(from_utc_timestamp(admitted_at, 'America/Chicago'))   AS admit_day,
           to_date(from_utc_timestamp(discharged_at, 'America/Chicago')) AS discharge_day
    FROM ${catalog}.gold.readmission_events
),

-- Stay cost and length come from readmission_events.
idx AS (
    SELECT *
    FROM stays
    WHERE is_index_stay
),

conds AS (
    SELECT i.patient_id, i.stay_no,
           count(DISTINCT c.source_code)       AS conditions_at_admit,
           max(mc.measure = 'diabetes_hba1c')  AS has_diabetes,
           max(mc.measure = 'bp_control')      AS has_hypertension,
           max(mc.measure = 'statin_therapy')  AS has_cardiovascular_disease
    FROM idx i
    JOIN ${catalog}.silver.condition c
      ON c.patient_id = i.patient_id
     AND c.onset_date <= i.admit_day
     AND (c.resolved_date IS NULL OR c.resolved_date >= i.admit_day)
    LEFT JOIN ${catalog}.gold.measure_code mc
      ON mc.role = 'denominator' AND mc.source = 'condition' AND mc.code = c.source_code
    GROUP BY i.patient_id, i.stay_no
),

prior_stays AS (
    SELECT i.patient_id, i.stay_no, count(p.stay_no) AS prior_stays_12m
    FROM idx i
    LEFT JOIN stays p
      ON p.patient_id = i.patient_id
     AND datediff(i.admit_day, p.admit_day) BETWEEN 1 AND 365
    GROUP BY i.patient_id, i.stay_no
),

prior_emergency AS (
    SELECT i.patient_id, i.stay_no, count(f.encounter_id) AS prior_emergency_12m
    FROM idx i
    LEFT JOIN ${catalog}.gold.fact_encounter f
      ON f.patient_id = i.patient_id
     AND f.encounter_class = 'emergency'
     AND datediff(i.admit_day, to_date(from_utc_timestamp(f.started_at, 'America/Chicago')))
         BETWEEN 1 AND 365
    GROUP BY i.patient_id, i.stay_no
),

followup AS (
    -- GROUP BY, not DISTINCT: a joined DISTINCT CTE stopped deduplicating in the pipeline (E58, E59).
    SELECT i.patient_id, i.stay_no, count(*) AS followup_visits
    FROM idx i
    JOIN ${catalog}.gold.fact_encounter f
      ON f.patient_id = i.patient_id
     AND f.canonical_class IN ('ambulatory', 'preventive')
    WHERE datediff(to_date(from_utc_timestamp(f.started_at, 'America/Chicago')), i.discharge_day)
          BETWEEN 1 AND least(7, coalesce(i.days_to_next_stay - 1, 7))
    GROUP BY i.patient_id, i.stay_no
),

-- The unplanned stay that made this one a readmission, for its cost.
return_cost AS (
    SELECT i.patient_id, i.stay_no, b.stay_claim_cost AS outcome_return_stay_cost
    FROM idx i
    JOIN stays b
      ON b.patient_id = i.patient_id
     AND b.stay_no > i.stay_no
     AND NOT b.is_planned
     AND datediff(b.admit_day, i.discharge_day) = i.days_to_unplanned_return
),

-- Coronary bypass from the day before admission: a feature and the population split.
bypass AS (
    SELECT i.patient_id, i.stay_no, count(*) AS bypass_procedures
    FROM idx i
    JOIN ${catalog}.silver.procedure p
      ON p.patient_id = i.patient_id
     AND p.source_code IN ('232717009', '418824004', '414088005')
     AND to_date(from_utc_timestamp(p.started_at, 'America/Chicago'))
         BETWEEN date_sub(i.admit_day, 1) AND i.discharge_day
    GROUP BY i.patient_id, i.stay_no
),

-- Any earlier stay, index or not. NULL for a patient's first stay.
last_discharge AS (
    SELECT i.patient_id, i.stay_no,
           datediff(i.admit_day, max(p.discharge_day)) AS days_since_last_discharge
    FROM idx i
    LEFT JOIN stays p ON p.patient_id = i.patient_id AND p.stay_no < i.stay_no
    GROUP BY i.patient_id, i.stay_no, i.admit_day
),

-- An emergency visit on the admit day or the day before.
via_emergency AS (
    SELECT i.patient_id, i.stay_no, count(*) AS emergency_visits
    FROM idx i
    JOIN ${catalog}.gold.fact_encounter f
      ON f.patient_id = i.patient_id
     AND f.encounter_class = 'emergency'
     AND datediff(i.admit_day, to_date(from_utc_timestamp(f.started_at, 'America/Chicago')))
         BETWEEN 0 AND 1
    GROUP BY i.patient_id, i.stay_no
),

joined AS (
    SELECT i.patient_id,
           i.stay_no,
           i.first_encounter_id,
           year(i.admit_day)                                                AS admit_year,
           -- 90 means "90 or older" (Safe Harbor, as patient_360).
           least(floor(months_between(i.admit_day, p.birth_date) / 12), 90) AS age_at_admit,
           p.GENDER                                                         AS gender,
           coalesce(c.has_diabetes, false)                                  AS has_diabetes,
           coalesce(c.has_hypertension, false)                              AS has_hypertension,
           coalesce(c.has_cardiovascular_disease, false)                    AS has_cardiovascular_disease,
           coalesce(c.conditions_at_admit, 0)                               AS conditions_at_admit,
           coalesce(i.admit_reason, 'no reason recorded')                   AS admit_reason,
           i.is_planned,
           i.length_of_stay_days,
           ps.prior_stays_12m,
           pe.prior_emergency_12m,
           i.encounters_in_stay,
           ld.days_since_last_discharge,
           bp.patient_id IS NOT NULL                                        AS had_bypass_surgery,
           ve.patient_id IS NOT NULL                                        AS arrived_via_emergency,
           i.admit_day,
           i.discharge_day,
           i.stay_claim_cost,
           fu.patient_id IS NOT NULL                                        AS post_followup_7d,
           i.readmitted_30d                                                 AS outcome_readmitted_30d,
           i.days_to_unplanned_return                                       AS outcome_days_to_return,
           rc.outcome_return_stay_cost
    FROM idx i
    JOIN ${catalog}.silver.patient p   ON p.patient_id = i.patient_id
    JOIN prior_stays ps                ON ps.patient_id = i.patient_id AND ps.stay_no = i.stay_no
    JOIN prior_emergency pe            ON pe.patient_id = i.patient_id AND pe.stay_no = i.stay_no
    JOIN last_discharge ld             ON ld.patient_id = i.patient_id AND ld.stay_no = i.stay_no
    LEFT JOIN bypass bp                ON bp.patient_id = i.patient_id AND bp.stay_no = i.stay_no
    LEFT JOIN via_emergency ve         ON ve.patient_id = i.patient_id AND ve.stay_no = i.stay_no
    LEFT JOIN conds c                  ON c.patient_id = i.patient_id AND c.stay_no = i.stay_no
    LEFT JOIN followup fu              ON fu.patient_id = i.patient_id AND fu.stay_no = i.stay_no
    LEFT JOIN return_cost rc           ON rc.patient_id = i.patient_id AND rc.stay_no = i.stay_no
),

cut AS (
    SELECT median(conditions_at_admit) AS conditions_median,
           median(length_of_stay_days) AS length_of_stay_median
    FROM joined
),

-- Top five admit reasons by count, ties by name; the rest are "other".
top_reason AS (
    SELECT admit_reason,
           row_number() OVER (ORDER BY count(*) DESC, admit_reason) AS reason_rank
    FROM joined
    GROUP BY admit_reason
)

SELECT j.patient_id,
       j.stay_no,
       -- The stay's stable key; stay_no can renumber (D81).
       j.first_encounter_id,
       j.admit_year,
       j.age_at_admit,
       CASE WHEN j.age_at_admit < 18 THEN '0-17'
            WHEN j.age_at_admit < 45 THEN '18-44'
            WHEN j.age_at_admit < 65 THEN '45-64'
            WHEN j.age_at_admit < 80 THEN '65-79'
            ELSE '80+' END                                        AS age_band,
       j.gender,
       j.has_diabetes,
       j.has_hypertension,
       j.has_cardiovascular_disease,
       j.conditions_at_admit,
       j.conditions_at_admit > k.conditions_median                AS above_median_conditions,
       j.admit_reason,
       CASE WHEN t.reason_rank <= 5 THEN j.admit_reason ELSE 'other' END AS admit_reason_group,
       j.is_planned,
       j.length_of_stay_days,
       j.length_of_stay_days > k.length_of_stay_median            AS above_median_length_of_stay,
       j.prior_stays_12m,
       j.prior_emergency_12m,
       j.encounters_in_stay,
       j.days_since_last_discharge,
       j.had_bypass_surgery,
       j.arrived_via_emergency,
       j.admit_day,
       j.discharge_day,
       j.stay_claim_cost,
       j.post_followup_7d,
       j.outcome_readmitted_30d,
       j.outcome_days_to_return,
       j.outcome_return_stay_cost,
       -- Not a feature: the one-row-per-stay gate reads it (E59).
       count(*) OVER (PARTITION BY j.first_encounter_id)            AS key_copies
FROM joined j
CROSS JOIN cut k
JOIN top_reason t ON t.admit_reason = j.admit_reason;