-- Silver's keys are unique (D81). Every gold total is checked against silver
-- (gold_checks: fact_rows_off and the rest), so a patient or visit landed
-- twice, by a re-upload under a new file name, would double in silver and in
-- gold alike and pass every one of those checks. These two are what catch it.
--
-- Like gold_checks: one row of counts, each gate NULL-safe (E57), and it runs
-- after the tables it reads, so it fails the update rather than protecting
-- the tables; gold, built from them, fails in the same update.

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW silver_checks (
    CONSTRAINT duplicate_patient_id EXPECT (duplicate_patient_id <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT duplicate_encounter_id EXPECT (duplicate_encounter_id <=> 0) ON VIOLATION FAIL UPDATE
)
AS
SELECT (SELECT count(*) - count(DISTINCT patient_id) FROM ${catalog}.silver.patient)
           AS duplicate_patient_id,
       (SELECT count(*) - count(DISTINCT encounter_id) FROM ${catalog}.silver.encounter)
           AS duplicate_encounter_id;
