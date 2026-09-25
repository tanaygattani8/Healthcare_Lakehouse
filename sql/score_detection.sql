-- Phase 3b step 5 — mark every program against the answer sheet, test set only.
--
-- A guess is right if it overlaps a real item of the same kind. Overlap, not
-- exact match: finding 'Babara Isadora' where the sheet has 'Babara' and
-- 'Isadora' separately is not a failure.
--
--   recall    = real items hit by at least one guess / real items
--   precision = guesses that hit at least one real item / guesses
--
-- The two need DIFFERENT top numbers. The first version used "guesses that
-- hit" for both, and guesses and real items are not one-to-one: the name model
-- split one date into four pieces (recall came out 1.053) and the language
-- model covered two names with one guess (recall came out 0.88, really
-- 0.996). errors.md E45.
--
-- Kinds with no real items are kept (real_items is NULL). Every guess there
-- is a false alarm — flagged ages under 90, insurers, drug doses read as ZIP
-- codes — and joining them away made every program look cleaner than it is.
--
-- recall is the column that matters: a miss is a real name left in a document.
--
-- Two stricter rules, reported so the choice is made with all three in view
-- (decision.md D54):
--   exact_recall   - some guess starts and ends exactly where the real item
--                    does. Punishes 'Babara Isadora' for hiding two names.
--   covered_recall - some ONE guess spans the whole real item. What
--                    de-identification needs: overlap counts 'Luc' as
--                    finding 'Lucius' and leaves 'ius' in the document.
--
-- Saved to ops.detection_score, the one place the MLflow runs and the app's
-- snapshot read from. Counts only — no text.

CREATE OR REPLACE TABLE healthcare_dev.ops.detection_score
COMMENT "Phase 3b marks: each detection program against the answer sheet, 25 test patients. Counts only."
AS

WITH heldout AS (SELECT patient_id FROM healthcare_dev.ops.heldout_patient),

truth AS (
    SELECT s.*, concat_ws(':', s.patient_id, s.char_start, s.char_end, s.phi_category) AS truth_id
    FROM healthcare_dev.silver.phi_span s JOIN heldout USING (patient_id)
),

guess AS (
    SELECT d.*, concat_ws(':', d.stage, d.patient_id, d.char_start, d.char_end, d.phi_category) AS guess_id
    FROM healthcare_dev.ops.detection_span d JOIN heldout USING (patient_id)
),

-- every (guess, real item) pair that overlaps, same patient, same kind
pairs AS (
    SELECT g.stage, g.phi_category, g.guess_id, t.truth_id,
           g.char_start = t.char_start AND g.char_end = t.char_end AS exact,
           g.char_start <= t.char_start AND g.char_end >= t.char_end AS covered
    FROM guess g
    JOIN truth t
      ON  g.patient_id   = t.patient_id
      AND g.phi_category = t.phi_category
      AND g.char_start   < t.char_end
      AND t.char_start   < g.char_end
),

matched AS (
    SELECT stage, phi_category,
           count(DISTINCT guess_id) AS guesses_right,
           count(DISTINCT truth_id) AS real_hit,
           count(DISTINCT CASE WHEN exact THEN truth_id END) AS real_hit_exact,
           count(DISTINCT CASE WHEN covered THEN truth_id END) AS real_hit_covered
    FROM pairs GROUP BY stage, phi_category
),

guesses AS (
    SELECT stage, phi_category, count(DISTINCT guess_id) AS guesses
    FROM guess GROUP BY stage, phi_category
),

reals AS (
    SELECT phi_category, count(*) AS real_items FROM truth GROUP BY phi_category
),

scored AS (
    SELECT g.stage, g.phi_category, r.real_items, g.guesses,
           coalesce(m.guesses_right, 0) AS guesses_right,
           coalesce(m.real_hit, 0)      AS real_hit,
           coalesce(m.guesses_right, 0) / g.guesses AS precision,
           m.real_hit / r.real_items                AS recall,
           m.real_hit_exact / r.real_items          AS exact_recall,
           m.real_hit_covered / r.real_items        AS covered_recall
    FROM guesses g
    LEFT JOIN reals r   USING (phi_category)
    LEFT JOIN matched m USING (stage, phi_category)
)

SELECT stage, phi_category, real_items, guesses, guesses_right, real_hit,
       round(precision, 3) AS precision,
       round(recall, 3)    AS recall,
       round(2 * precision * recall / nullif(precision + recall, 0), 3) AS f1,
       round(exact_recall, 3)   AS exact_recall,
       round(covered_recall, 3) AS covered_recall
FROM scored;

SELECT stage, phi_category, real_items, guesses, precision,
       recall, covered_recall, exact_recall
FROM healthcare_dev.ops.detection_score
ORDER BY real_items IS NULL, phi_category, stage;
