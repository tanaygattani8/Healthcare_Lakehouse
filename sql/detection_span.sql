-- Phase 3b step 4: one table every detection program writes, test-set patients only (D51).

CREATE TABLE IF NOT EXISTS healthcare_dev.ops.detection_span (
    stage        STRING,
    patient_id   STRING,
    char_start   INT,
    char_end     INT,
    phi_category STRING,
    surface_text STRING
)
COMMENT "What each detection program found in the test-set notes, one row per hit.";

-- Raw model replies, kept for re-parsing; they quote names and dates.
CREATE TABLE IF NOT EXISTS healthcare_dev.ops.llm_reply (
    patient_id  STRING,
    chunk_index INT,
    reply       STRING,
    error       STRING
)
COMMENT "Language-model replies per note piece, for Program 3. Parsed locally by scripts/detect_llm.py.";

-- Both hold real details; ops already carries the policies, so tags suffice.
ALTER TABLE healthcare_dev.ops.detection_span
  ALTER COLUMN surface_text SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.ops.llm_reply
  ALTER COLUMN reply SET TAGS ('phi_category' = 'name');

-- Program 0: the answer key itself; must score 100%, or the marking is wrong.
DELETE FROM healthcare_dev.ops.detection_span WHERE stage = 'roster';
INSERT INTO healthcare_dev.ops.detection_span
SELECT 'roster', s.patient_id, s.char_start, s.char_end, s.phi_category, s.surface_text
FROM healthcare_dev.silver.phi_span s
JOIN healthcare_dev.ops.heldout_patient h USING (patient_id);

SELECT stage, phi_category, count(*) AS hits, count(DISTINCT patient_id) AS patients
FROM healthcare_dev.ops.detection_span
GROUP BY stage, phi_category ORDER BY stage, hits DESC;
