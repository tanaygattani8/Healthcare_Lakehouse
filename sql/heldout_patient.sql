-- Phase 3b step 2: the test set, fixed before any program ran; md5 order keeps it repeatable.
-- 25 patients, not 200, for every stage: the NER model needs 3.9 s a piece on CPU (D51).

CREATE OR REPLACE TABLE healthcare_dev.ops.heldout_patient
COMMENT "The 25 patients every detection program is scored on. Chosen before any program existed; cut from 200 to 25 for CPU cost, same shuffle order."
AS
SELECT patient_id
FROM healthcare_dev.silver.patient
ORDER BY md5(patient_id)
LIMIT 25;

SELECT count(*) AS heldout,
       (SELECT count(*) FROM healthcare_dev.silver.note_chunk c
         JOIN healthcare_dev.ops.heldout_patient h USING (patient_id)) AS pieces_to_process
FROM healthcare_dev.ops.heldout_patient;
