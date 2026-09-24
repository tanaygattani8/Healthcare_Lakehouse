-- Phase 3b step 3 — the answer sheet, as a table.
--
-- Built locally by scripts/build_answer_key.py (the notes and the patient
-- details are both needed, and the join is by exact text search), uploaded to
-- the landing volume, then read here. The volume already holds the notes, so
-- the CSV adds no exposure the notes did not already have.

CREATE OR REPLACE TABLE healthcare_dev.silver.phi_span
COMMENT "Answer sheet: every real patient detail inside every note, with its exact position. Scoring target for phase 3b."
AS
SELECT * FROM read_files(
    '/Volumes/healthcare_dev/bronze/landing/phi_span/',
    format => 'csv', header => true,
    schema => 'patient_id STRING, char_start INT, char_end INT, phi_category STRING, surface_text STRING'
);

-- surface_text holds names, dates and ages mixed together. 'name' gives it the
-- strongest mask ('***') rather than date's year-only, because a partly
-- masked name is still a name. Positions stay readable: without the note text
-- they point at nothing.
ALTER TABLE healthcare_dev.silver.phi_span
  ALTER COLUMN surface_text SET TAGS ('phi_category' = 'name');

SELECT phi_category, count(*) AS spans, count(DISTINCT patient_id) AS patients
FROM healthcare_dev.silver.phi_span
GROUP BY phi_category ORDER BY spans DESC;

-- Must be 0: the CSV parsed cleanly and no position is recorded twice.
SELECT sum(CASE WHEN char_start IS NULL OR char_end IS NULL THEN 1 ELSE 0 END) AS unparsed,
       count(*) - count(DISTINCT patient_id, char_start, char_end) AS duplicates
FROM healthcare_dev.silver.phi_span;
