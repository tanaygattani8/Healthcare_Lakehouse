-- P2. Overlapping hospital stays today. The gate found 122 on older data.
WITH inp AS (
    SELECT patient_id, started_at, stopped_at,
           lag(stopped_at) OVER (PARTITION BY patient_id ORDER BY started_at) AS prev_stop
    FROM healthcare_dev.silver.encounter
    WHERE readmission_role = 'index_eligible'
)
SELECT count(*) AS inpatient_encounters,
       count_if(started_at < prev_stop) AS starts_before_previous_ended,
       count_if(to_date(started_at) = to_date(prev_stop)) AS starts_same_day_previous_ended
FROM inp;

-- P3. Why people are admitted. Decides which readmissions count as
-- "planned" (a scheduled procedure, not a relapse). Top 25 reasons.
SELECT coalesce(reason_description, '(none)') AS reason, count(*) AS stays
FROM healthcare_dev.silver.encounter
WHERE readmission_role = 'index_eligible'
GROUP BY 1 ORDER BY stays DESC LIMIT 25;

-- P4. The codes the care-gap measures need. Each must be > 0.
SELECT 'diabetes 44054006' AS code, count(DISTINCT patient_id) AS patients
  FROM healthcare_dev.silver.condition WHERE source_code = '44054006'
UNION ALL SELECT 'hypertension 59621000', count(DISTINCT patient_id)
  FROM healthcare_dev.silver.condition WHERE source_code = '59621000'
UNION ALL SELECT 'coronary 53741008', count(DISTINCT patient_id)
  FROM healthcare_dev.silver.condition WHERE source_code = '53741008'
UNION ALL SELECT 'MI 22298006', count(DISTINCT patient_id)
  FROM healthcare_dev.silver.condition WHERE source_code = '22298006'
UNION ALL SELECT 'stroke 230690007', count(DISTINCT patient_id)
  FROM healthcare_dev.silver.condition WHERE source_code = '230690007'
UNION ALL SELECT 'HbA1c 4548-4', count(DISTINCT patient_id)
  FROM healthcare_dev.silver.observation WHERE source_code = '4548-4'
UNION ALL SELECT 'systolic 8480-6', count(DISTINCT patient_id)
  FROM healthcare_dev.silver.observation WHERE source_code = '8480-6'
UNION ALL SELECT 'diastolic 8462-4', count(DISTINCT patient_id)
  FROM healthcare_dev.silver.observation WHERE source_code = '8462-4'
UNION ALL SELECT 'BMI 39156-5', count(DISTINCT patient_id)
  FROM healthcare_dev.silver.observation WHERE source_code = '39156-5'
UNION ALL SELECT 'a statin, by name', count(DISTINCT patient_id)
  FROM healthcare_dev.silver.medication
  WHERE lower(source_description) RLIKE '\\b(simva|atorva|rosuva|prava|lova|fluva|pitava)statin\\b'
-- The trap: "nystatin" is an antifungal and contains "statin". Matching
-- '%statin%' would count every thrush prescription as heart protection.
UNION ALL SELECT 'nystatin (must NOT count)', count(DISTINCT patient_id)
  FROM healthcare_dev.silver.medication WHERE lower(source_description) LIKE '%nystatin%';

-- If a code above is 0, find what Synthea calls it instead:
SELECT source_code, source_description, count(DISTINCT patient_id) AS patients
FROM healthcare_dev.silver.condition
WHERE lower(source_description) RLIKE 'diabetes|hypertension|coronary|infarction|stroke'
GROUP BY 1, 2 ORDER BY patients DESC LIMIT 20;

-- P5. Where the data ends, so "last complete year" means something.
SELECT min(started_at) AS first_visit, max(started_at) AS last_visit,
       year(max(started_at)) - 1 AS last_complete_year
FROM healthcare_dev.silver.encounter;

-- P7. Reference-table columns, for step 1.
DESCRIBE healthcare_dev.bronze.br_providers;
DESCRIBE healthcare_dev.bronze.br_organizations;
DESCRIBE healthcare_dev.bronze.br_payers;
