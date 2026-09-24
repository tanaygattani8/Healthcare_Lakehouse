-- Phase 3b step 4 — load the programs that run on the laptop.
--
-- scripts/detect_regex.py and scripts/detect_llm.py each write a CSV to
-- data/detections/, which is uploaded to the landing volume with:
--   databricks fs cp -r --overwrite data/detections dbfs:/Volumes/healthcare_dev/bronze/landing/detections
-- Every CSV carries its own `stage` column, so this file loads whichever are
-- there and replaces those stages only. Safe to re-run.

CREATE OR REPLACE TEMPORARY VIEW incoming AS
SELECT * FROM read_files(
    '/Volumes/healthcare_dev/bronze/landing/detections/',
    format => 'csv', header => true,
    schema => 'stage STRING, patient_id STRING, char_start INT, char_end INT, phi_category STRING, surface_text STRING'
);

DELETE FROM healthcare_dev.ops.detection_span
WHERE stage IN (SELECT DISTINCT stage FROM incoming);

INSERT INTO healthcare_dev.ops.detection_span SELECT * FROM incoming;

SELECT stage, phi_category, count(*) AS hits, count(DISTINCT patient_id) AS patients
FROM healthcare_dev.ops.detection_span
GROUP BY stage, phi_category ORDER BY stage, hits DESC;
