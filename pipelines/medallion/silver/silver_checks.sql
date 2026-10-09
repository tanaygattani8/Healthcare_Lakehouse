-- Silver's keys are unique (D81): a duplicate would double silver and gold alike and pass gold_checks.

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW silver_checks (
    CONSTRAINT duplicate_patient_id EXPECT (duplicate_patient_id <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT duplicate_encounter_id EXPECT (duplicate_encounter_id <=> 0) ON VIOLATION FAIL UPDATE
)
AS
SELECT (SELECT count(*) - count(DISTINCT patient_id) FROM ${catalog}.silver.patient)
           AS duplicate_patient_id,
       (SELECT count(*) - count(DISTINCT encounter_id) FROM ${catalog}.silver.encounter)
           AS duplicate_encounter_id;
