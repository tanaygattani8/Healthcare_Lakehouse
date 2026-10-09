-- Synthea's ten encounter classes in one lookup table, so readmission logic has one definition.
-- Adds post_acute (snf, hospice) and readmission_role, beyond the spec.
-- index_eligible starts a window; transfer_target is not a readmission; excluded and not_applicable never count.

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


-- Must stay empty: an unmapped class fails the update (D73).
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.unmapped_encounter_class (
    CONSTRAINT every_class_mapped EXPECT (false) ON VIOLATION FAIL UPDATE
)
COMMENT "Must be empty. Any row here is an encounter class nothing maps."
AS
SELECT DISTINCT e.ENCOUNTERCLASS AS encounter_class
FROM ${catalog}.bronze.br_encounters e
LEFT JOIN ${catalog}.silver.encounter_class_map m
    ON e.ENCOUNTERCLASS = m.encounter_class
WHERE m.encounter_class IS NULL
