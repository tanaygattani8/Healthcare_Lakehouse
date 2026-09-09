-- One row per patient.
--
-- All identifying columns live here and nowhere else. Phase 3 strips exactly
-- this table, so keeping them together is the point, not an accident.
--
-- The quarantine pattern used by every silver table:
--   v_<name>  -- typed, with a violations array
--   <name>    -- valid rows only, in silver
--   ops.quarantine_<name> -- failing rows kept whole, never deleted
--
-- Databricks has no built-in quarantine. EXPECT ... ON VIOLATION DROP ROW
-- deletes the row and keeps a count; the row itself is gone. Splitting the
-- typed view in two is how the row survives.

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.v_patient AS
SELECT
    Id                                        AS patient_id,
    TRY_CAST(BIRTHDATE AS DATE)               AS birth_date,
    TRY_CAST(NULLIF(DEATHDATE, '') AS DATE)   AS death_date,
    NULLIF(DEATHDATE, '') IS NOT NULL         AS is_deceased,

    -- identifying columns, deliberately grouped
    SSN, DRIVERS, PASSPORT,
    PREFIX, FIRST, MIDDLE, LAST, SUFFIX, MAIDEN,
    ADDRESS, CITY, STATE, COUNTY, ZIP, FIPS,
    TRY_CAST(LAT AS DOUBLE)                   AS latitude,
    TRY_CAST(LON AS DOUBLE)                   AS longitude,
    BIRTHPLACE,

    MARITAL, RACE, ETHNICITY, GENDER,
    TRY_CAST(HEALTHCARE_EXPENSES AS DOUBLE)   AS healthcare_expenses,
    TRY_CAST(HEALTHCARE_COVERAGE AS DOUBLE)   AS healthcare_coverage,
    TRY_CAST(INCOME AS DOUBLE)                AS income,

    _source_file, _ingested_at, _batch_id,

    filter(array(
        CASE WHEN TRY_CAST(BIRTHDATE AS DATE) IS NULL
             THEN 'birth_date_unparseable' END,
        CASE WHEN TRY_CAST(BIRTHDATE AS DATE) > current_date()
             THEN 'birth_date_in_future' END,
        CASE WHEN NULLIF(DEATHDATE, '') IS NOT NULL
              AND TRY_CAST(DEATHDATE AS DATE) < TRY_CAST(BIRTHDATE AS DATE)
             THEN 'death_before_birth' END,
        CASE WHEN Id IS NULL OR Id = '' THEN 'missing_patient_id' END
    ), x -> x IS NOT NULL)                    AS violations
FROM ${catalog}.bronze.br_patients;


CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.patient
(
    CONSTRAINT valid_patient EXPECT (size(violations) = 0) ON VIOLATION DROP ROW
)
COMMENT "One row per patient. All PII concentrates here; phase 3 targets it."
TBLPROPERTIES ("quality" = "silver")
AS SELECT * FROM ${catalog}.silver.v_patient;


CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.ops.quarantine_patient
COMMENT "Patients that failed a rule. Kept whole, never discarded."
AS SELECT * FROM ${catalog}.silver.v_patient WHERE size(violations) > 0;
