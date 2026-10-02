-- Each metric view must give gold's known numbers (D58, and Task 2).

-- Expect stays 14313, encounters_merged 1382, excluded_died 173,
-- excluded_short_followup 30, excluded_hospice 0, excluded_cancer_treatment 3402,
-- index_stays 10724 (D65; the exclusions overlap).
SELECT MEASURE(stays), MEASURE(encounters_merged), MEASURE(excluded_died),
       MEASURE(excluded_short_followup), MEASURE(excluded_hospice),
       MEASURE(excluded_cancer_treatment), MEASURE(index_stays)
FROM healthcare_dev.metrics.stays;

-- Expect 10724, 173, 1.61, and readmitted_patients 158.
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
