-- Phase 3b step 2 — fix the test set NOW, before any program has been run.
--
-- Choosing which notes to score on after seeing results is how a flattering
-- number gets manufactured. This is created once and not touched again.
--
-- md5 of the id gives a shuffled but repeatable order, so re-running this
-- returns exactly the same patients rather than a fresh random draw. Cutting
-- from 200 to 25 therefore keeps the first 25 of the same shuffle — a subset,
-- not a different sample, so nothing about the selection changed except how
-- many were kept.
--
-- Why 25 and not 200 (decision.md D51). The only model that finds real
-- patient names, obi/deid_roberta_i2b2, runs at 3.9s per piece on CPU and
-- batching does not help — 200 patients is 41,592 pieces, or 45 hours. The
-- language model has the same problem from the other side: 41,592 ai_query
-- calls is roughly 23 more hours.
--
-- The cut applies to EVERY stage, not just the slow one. Scoring stages on
-- different data would destroy the only comparison this phase exists to make.
--
-- 25 patients is still thousands of measurements: a first name appears about
-- 89 times per note, so this is roughly 2,200 name occurrences and a similar
-- number of dates. What it costs is real and is stated wherever the numbers
-- are: per-note F1 across 25 notes, not across the corpus.

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
