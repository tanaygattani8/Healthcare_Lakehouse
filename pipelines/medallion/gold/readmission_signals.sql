CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.readmission_signals
COMMENT "One row per index stay. Never model features: post_* (known only after discharge), outcome_* (the answer), stay_claim_cost (the bill is not final at discharge), admit_year, and the keys patient_id, stay_no."
TBLPROPERTIES ("quality" = "gold")
AS
WITH stays AS (
    SELECT *,
           to_date(from_utc_timestamp(admitted_at, 'America/Chicago'))   AS admit_day,
           to_date(from_utc_timestamp(discharged_at, 'America/Chicago')) AS discharge_day
    FROM ${catalog}.gold.readmission_events
),

stay_cost AS (
    SELECT s.patient_id, s.stay_no, sum(f.total_claim_cost) AS stay_claim_cost
    FROM stays s
    JOIN ${catalog}.gold.fact_encounter f
      ON f.patient_id = s.patient_id
     AND f.readmission_role = 'index_eligible'
     AND to_date(from_utc_timestamp(f.started_at, 'America/Chicago'))
         BETWEEN s.admit_day AND s.discharge_day
    GROUP BY s.patient_id, s.stay_no
),

idx AS (
    SELECT s.*, c.stay_claim_cost
    FROM stays s
    JOIN stay_cost c ON c.patient_id = s.patient_id AND c.stay_no = s.stay_no
    WHERE s.is_index_stay
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
    SELECT DISTINCT i.patient_id, i.stay_no
    FROM idx i
    JOIN ${catalog}.gold.fact_encounter f
      ON f.patient_id = i.patient_id
     AND f.canonical_class IN ('ambulatory', 'preventive')
    WHERE datediff(to_date(from_utc_timestamp(f.started_at, 'America/Chicago')), i.discharge_day)
          BETWEEN 1 AND least(7, coalesce(i.days_to_next_stay - 1, 7))
),

-- The unplanned stay that made this one a readmission, for its cost.
return_cost AS (
    SELECT i.patient_id, i.stay_no, c.stay_claim_cost AS outcome_return_stay_cost
    FROM idx i
    JOIN stays b
      ON b.patient_id = i.patient_id
     AND b.stay_no > i.stay_no
     AND NOT b.is_planned
     AND datediff(b.admit_day, i.discharge_day) = i.days_to_unplanned_return
    JOIN stay_cost c ON c.patient_id = b.patient_id AND c.stay_no = b.stay_no
),

joined AS (
    SELECT i.patient_id,
           i.stay_no,
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
           datediff(i.discharge_day, i.admit_day)                           AS length_of_stay_days,
           ps.prior_stays_12m,
           pe.prior_emergency_12m,
           i.stay_claim_cost,
           fu.patient_id IS NOT NULL                                        AS post_followup_7d,
           i.readmitted_30d                                                 AS outcome_readmitted_30d,
           i.days_to_unplanned_return                                       AS outcome_days_to_return,
           rc.outcome_return_stay_cost
    FROM idx i
    JOIN ${catalog}.silver.patient p   ON p.patient_id = i.patient_id
    JOIN prior_stays ps                ON ps.patient_id = i.patient_id AND ps.stay_no = i.stay_no
    JOIN prior_emergency pe            ON pe.patient_id = i.patient_id AND pe.stay_no = i.stay_no
    LEFT JOIN conds c                  ON c.patient_id = i.patient_id AND c.stay_no = i.stay_no
    LEFT JOIN followup fu              ON fu.patient_id = i.patient_id AND fu.stay_no = i.stay_no
    LEFT JOIN return_cost rc           ON rc.patient_id = i.patient_id AND rc.stay_no = i.stay_no
),

cut AS (
    SELECT median(conditions_at_admit) AS conditions_median,
           median(length_of_stay_days) AS length_of_stay_median
    FROM joined
),

-- The five commonest admit reasons keep their name; the rest are "other".
-- Ties are broken by name, so every rebuild picks the same five.
top_reason AS (
    SELECT admit_reason,
           row_number() OVER (ORDER BY count(*) DESC, admit_reason) AS reason_rank
    FROM joined
    GROUP BY admit_reason
)

SELECT j.patient_id,
       j.stay_no,
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
       j.stay_claim_cost,
       j.post_followup_7d,
       j.outcome_readmitted_30d,
       j.outcome_days_to_return,
       j.outcome_return_stay_cost
FROM joined j
CROSS JOIN cut k
JOIN top_reason t ON t.admit_reason = j.admit_reason;