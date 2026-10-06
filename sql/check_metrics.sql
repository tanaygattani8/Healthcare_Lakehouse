-- Each metric view must give gold's known numbers (D58, and Task 2).

-- Expect stays 14313, encounters_merged 1382, excluded_died 173,
-- excluded_short_followup 30, excluded_hospice 0, excluded_cancer_treatment 3402,
-- index_stays 10724 (D65; the exclusions overlap).
SELECT MEASURE(stays), MEASURE(encounters_merged), MEASURE(excluded_died),
       MEASURE(excluded_short_followup), MEASURE(excluded_hospice),
       MEASURE(excluded_cancer_treatment), MEASURE(index_stays)
FROM healthcare_dev.metrics.stays;

-- Expect 10724, 140, 1.31, and readmitted_patients 127 (D68).
SELECT MEASURE(index_stays), MEASURE(readmitted), round(MEASURE(readmission_rate_pct), 2),
       MEASURE(patients), MEASURE(readmitted_patients)
FROM healthcare_dev.metrics.readmission;

-- The same two patient counts straight from gold: must equal the row above.
SELECT count(DISTINCT patient_id),
       count(DISTINCT CASE WHEN outcome_readmitted_30d THEN patient_id END)
FROM healthcare_dev.gold.readmission_signals;

-- A banded dimension adds back to 10724: expect 0, 1, 2+.
SELECT prior_stays_12m_band, MEASURE(index_stays), MEASURE(readmitted)
FROM healthcare_dev.metrics.readmission
GROUP BY ALL ORDER BY prior_stays_12m_band;

-- A filter on a dimension, as Task 10 uses it: the rest of the stays.
SELECT MEASURE(index_stays), MEASURE(readmitted)
FROM healthcare_dev.metrics.readmission
WHERE cast(prior_stays_12m_band AS STRING) <> '0';

-- Phase 8. The privacy rule: expect NULL, 1.0, 0.0, NULL.
SELECT healthcare_dev.metrics.shown(5, 1.0), healthcare_dev.metrics.shown(11, 1.0),
       healthcare_dev.metrics.shown(0, 0.0), healthcare_dev.metrics.shown(NULL, 1.0);

-- Phase 8. The windows: four month starts, window_start 11 months before
-- last_month, prior_end 1 month before window_start.
SELECT * FROM healthcare_dev.metrics.kpi_window;

-- Phase 8. Visits: counted once, and the joins neither drop nor copy any.
-- Expect 0 in every column.
WITH total AS (SELECT MEASURE(visits) AS v FROM healthcare_dev.metrics.operations),
by_hospital AS (SELECT hospital, MEASURE(visits) AS v FROM healthcare_dev.metrics.operations GROUP BY ALL),
by_payer AS (SELECT payer, MEASURE(visits) AS v FROM healthcare_dev.metrics.operations GROUP BY ALL)
SELECT (SELECT v FROM total) - (SELECT count(*) FROM healthcare_dev.gold.fact_encounter) AS visits_off,
       (SELECT sum(v) FROM by_hospital) - (SELECT v FROM total) AS hospital_split_off,
       (SELECT sum(v) FROM by_payer) - (SELECT v FROM total) AS payer_split_off,
       (SELECT count_if(hospital IS NULL OR hospital = '') FROM by_hospital) AS unnamed_hospitals,
       (SELECT count_if(payer IS NULL) FROM by_payer) AS unnamed_payers;

-- Phase 8. Stays after the joins: every stay and every dollar once.
-- Expect 0 in every column.
WITH total AS (SELECT MEASURE(stays) AS n, MEASURE(stay_cost) AS c FROM healthcare_dev.metrics.stays),
by_hospital AS (SELECT hospital, MEASURE(stays) AS n, MEASURE(stay_cost) AS c FROM healthcare_dev.metrics.stays GROUP BY ALL),
by_payer AS (SELECT payer, MEASURE(stays) AS n FROM healthcare_dev.metrics.stays GROUP BY ALL)
SELECT (SELECT n FROM total) - (SELECT count(*) FROM healthcare_dev.gold.readmission_events) AS stays_off,
       (SELECT c FROM total) - (SELECT sum(stay_claim_cost) FROM healthcare_dev.gold.readmission_events) AS cost_off,
       (SELECT sum(n) FROM by_hospital) - (SELECT n FROM total) AS hospital_split_off,
       (SELECT sum(c) FROM by_hospital) - (SELECT c FROM total) AS hospital_cost_split_off,
       (SELECT sum(n) FROM by_payer) - (SELECT n FROM total) AS payer_split_off,
       (SELECT count_if(hospital IS NULL OR hospital = '') FROM by_hospital) AS unnamed_hospitals,
       (SELECT count_if(payer IS NULL) FROM by_payer) AS unnamed_payers;

-- Phase 8. Every hospital encounter's cost lands in exactly one stay: stay
-- costs add up to fact_encounter's index-eligible encounters. Expect 0.00.
SELECT (SELECT sum(stay_claim_cost) FROM healthcare_dev.gold.readmission_events)
     - (SELECT sum(total_claim_cost) FROM healthcare_dev.gold.fact_encounter
        WHERE readmission_role = 'index_eligible') AS stay_cost_vs_encounters_off;

-- Phase 8. care_gaps against care_gap, counted another way (closed = not a
-- gap). Expect one row per measure, both columns 0.
SELECT g.measure,
       g.eligible - c.eligible AS eligible_off,
       g.closed - c.closed AS closed_off
FROM (SELECT measure, MEASURE(eligible) AS eligible, MEASURE(closed) AS closed
      FROM healthcare_dev.metrics.care_gaps GROUP BY ALL) g
JOIN (SELECT measure,
             count_if(NOT (excl_age OR excl_died OR excl_hospice)) AS eligible,
             count_if(NOT (excl_age OR excl_died OR excl_hospice) AND NOT gap) AS closed
      FROM healthcare_dev.gold.care_gap GROUP BY measure) c
  ON c.measure = g.measure
ORDER BY g.measure;