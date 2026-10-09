-- Phase 3b step 4: load data/detections/*.csv, replacing only the stages present; re-runnable.

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
