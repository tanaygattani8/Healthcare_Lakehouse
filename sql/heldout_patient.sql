-- Phase 3b step 2 — fix the test set NOW, before any program has been run.
--
-- Choosing which notes to score on after seeing results is how a flattering
-- number gets manufactured. This is created once and not touched again.
--
-- md5 of the id gives a shuffled but repeatable order, so re-running this
-- returns exactly the same 200 patients rather than a fresh random draw.

CREATE OR REPLACE TABLE healthcare_dev.ops.heldout_patient
COMMENT "The 200 patients every detection program is scored on. Fixed 2026-09-23, before any program existed."
AS
SELECT patient_id
FROM healthcare_dev.silver.patient
ORDER BY md5(patient_id)
LIMIT 200;

SELECT count(*) AS heldout,
       (SELECT count(*) FROM healthcare_dev.silver.note_chunk c
         JOIN healthcare_dev.ops.heldout_patient h USING (patient_id)) AS pieces_to_process
FROM healthcare_dev.ops.heldout_patient;
