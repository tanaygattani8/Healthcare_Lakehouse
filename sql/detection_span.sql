-- Phase 3b step 4 — where every detection program writes, plus Program 0.
--
-- All four programs write rows of the same shape, tagged by `stage`, so the
-- marking query in step 5 is written once. Only the 25 test-set patients are
-- stored: every stage is scored on exactly the same notes (decision.md D51).

CREATE TABLE IF NOT EXISTS healthcare_dev.ops.detection_span (
    stage        STRING,
    patient_id   STRING,
    char_start   INT,
    char_end     INT,
    phi_category STRING,
    surface_text STRING
)
COMMENT "What each detection program found in the test-set notes, one row per hit.";

-- Raw language-model answers, kept so they can be re-parsed without paying
-- for the calls again. The replies quote names and dates from the notes.
CREATE TABLE IF NOT EXISTS healthcare_dev.ops.llm_reply (
    patient_id  STRING,
    chunk_index INT,
    reply       STRING,
    error       STRING
)
COMMENT "Language-model replies per note piece, for Program 3. Parsed locally by scripts/detect_llm.py.";

-- Both hold real patient details. The ops schema already carries the 3a
-- policies, so the tags are all that is needed.
ALTER TABLE healthcare_dev.ops.detection_span
  ALTER COLUMN surface_text SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.ops.llm_reply
  ALTER COLUMN reply SET TAGS ('phi_category' = 'name');

-- Program 0 — look up the patient's own details and search for them. This IS
-- the answer sheet, so it must score 100%. It is not a result: it proves the
-- marking query in step 5 works. Anything under 100% is a bug in the marking.
DELETE FROM healthcare_dev.ops.detection_span WHERE stage = 'roster';
INSERT INTO healthcare_dev.ops.detection_span
SELECT 'roster', s.patient_id, s.char_start, s.char_end, s.phi_category, s.surface_text
FROM healthcare_dev.silver.phi_span s
JOIN healthcare_dev.ops.heldout_patient h USING (patient_id);

SELECT stage, phi_category, count(*) AS hits, count(DISTINCT patient_id) AS patients
FROM healthcare_dev.ops.detection_span
GROUP BY stage, phi_category ORDER BY stage, hits DESC;
