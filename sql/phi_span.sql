-- Phase 3b step 3: the answer key built by build_answer_key.py, read from the landing volume.

CREATE OR REPLACE TABLE healthcare_dev.silver.phi_span
COMMENT "Answer sheet: every real patient detail inside every note, with its exact position. Scoring target for phase 3b."
AS
SELECT * FROM read_files(
    '/Volumes/healthcare_dev/bronze/landing/phi_span/',
    format => 'csv', header => true,
    schema => 'patient_id STRING, char_start INT, char_end INT, phi_category STRING, surface_text STRING'
);

-- surface_text mixes names, dates and ages, so it takes the strongest mask.
ALTER TABLE healthcare_dev.silver.phi_span
  ALTER COLUMN surface_text SET TAGS ('phi_category' = 'name');

SELECT phi_category, count(*) AS spans, count(DISTINCT patient_id) AS patients
FROM healthcare_dev.silver.phi_span
GROUP BY phi_category ORDER BY spans DESC;

-- Must be 0: the CSV parsed cleanly and no position is recorded twice.
SELECT sum(CASE WHEN char_start IS NULL OR char_end IS NULL THEN 1 ELSE 0 END) AS unparsed,
       count(*) - count(DISTINCT patient_id, char_start, char_end) AS duplicates
FROM healthcare_dev.silver.phi_span;
