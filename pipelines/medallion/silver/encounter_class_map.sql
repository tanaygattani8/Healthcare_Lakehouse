-- Synthea's ten encounter classes, mapped to a canonical taxonomy.
--
-- A lookup table rather than a CASE expression inside a query, because
-- scripts/readmission_gate.py already carries its own hardcoded notion of
-- "inpatient". Two places deciding that will eventually disagree, and a table
-- makes the disagreement visible.
--
-- TWO DELIBERATE DEVIATIONS FROM THE SPEC, both flagged for review:
--
-- 1. The spec names three canonical classes (acute / ambulatory / preventive).
--    This adds a fourth, post_acute, for snf and hospice. Those are facility
--    stays, so calling them ambulatory is wrong, and they are not acute care
--    either. The spec listed five encounter classes; the data has ten
--    (docs/silver-model-findings.md), so it never considered these.
--
-- 2. readmission_role is a second column the spec does not mention. One column
--    cannot answer both "what kind of care was this" and "does this count
--    toward readmission" -- and conflating them is how a transfer to skilled
--    nursing silently becomes a readmission.
--
-- readmission_role values:
--   index_eligible      -- can start a 30-day readmission window
--   transfer_target     -- where patients go after discharge; arriving here is
--                          not a readmission
--   excluded            -- removed from the measure entirely
--   not_applicable      -- outpatient care, irrelevant to the measure

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.encounter_class_map
COMMENT "Synthea encounter class to canonical taxonomy and readmission role."
TBLPROPERTIES ("quality" = "silver")
AS
SELECT * FROM VALUES
    ('inpatient',  'acute',      'index_eligible'),
    ('emergency',  'acute',      'not_applicable'),
    ('urgentcare', 'acute',      'not_applicable'),
    ('snf',        'post_acute', 'transfer_target'),
    ('hospice',    'post_acute', 'excluded'),
    ('ambulatory', 'ambulatory', 'not_applicable'),
    ('outpatient', 'ambulatory', 'not_applicable'),
    ('virtual',    'ambulatory', 'not_applicable'),
    ('home',       'ambulatory', 'not_applicable'),
    ('wellness',   'preventive', 'not_applicable')
AS t(encounter_class, canonical_class, readmission_role);


-- Every encounter class in bronze must appear above. An unmapped class would
-- otherwise become NULL and quietly drop encounters out of every denominator.
-- This view must stay empty; Task 7 attaches the expectation that enforces it.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.unmapped_encounter_class
COMMENT "Must be empty. Any row here is an encounter class nothing maps."
AS
SELECT DISTINCT e.ENCOUNTERCLASS AS encounter_class
FROM ${catalog}.bronze.br_encounters e
LEFT JOIN ${catalog}.silver.encounter_class_map m
    ON e.ENCOUNTERCLASS = m.encounter_class
WHERE m.encounter_class IS NULL
