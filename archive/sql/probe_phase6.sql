CREATE SCHEMA IF NOT EXISTS healthcare_dev.ml
COMMENT "Phase 6: models, scores, results and drift. Written by notebooks, not the pipeline.";

WITH idx AS (
    SELECT patient_id, stay_no,
           to_date(from_utc_timestamp(admitted_at, 'America/Chicago')) AS admit_day
    FROM healthcare_dev.gold.readmission_events
    WHERE is_index_stay
),
er AS (
    SELECT DISTINCT i.patient_id, i.stay_no
    FROM idx i
    JOIN healthcare_dev.gold.fact_encounter f
      ON f.patient_id = i.patient_id
     AND f.encounter_class = 'emergency'
     AND datediff(i.admit_day, to_date(from_utc_timestamp(f.started_at, 'America/Chicago')))
         BETWEEN 0 AND 1
)
SELECT count(*)                                         AS index_stays,
       round(100 * count(er.stay_no) / count(*), 1)     AS pct_via_emergency
FROM idx i
LEFT JOIN er ON er.patient_id = i.patient_id AND er.stay_no = i.stay_no;

WITH r AS (
    SELECT admit_reason,
           max(admit_year < 2020)          AS in_training,
           count_if(admit_year >= 2020)    AS prod_stays
    FROM healthcare_dev.gold.readmission_signals
    GROUP BY admit_reason
)
SELECT count_if(NOT in_training)                                              AS unseen_reasons,
       round(100 * sum(CASE WHEN NOT in_training THEN prod_stays END)
             / sum(prod_stays), 1)                                            AS pct_prod_stays_unseen,
       count_if(NOT in_training AND lower(admit_reason) LIKE '%coronavirus%') AS covid_reasons
FROM r;

-- P4, the names. Reason names are codes, not patients.
SELECT admit_reason
FROM healthcare_dev.gold.readmission_signals
GROUP BY admit_reason
HAVING max(admit_year < 2020) = false
ORDER BY admit_reason;