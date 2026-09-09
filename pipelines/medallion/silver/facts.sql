-- The remaining six clinical fact tables, all following the shape proved by
-- condition.sql: typed view with a violations array, valid rows to silver,
-- failing rows kept whole in ops.
--
-- The encounter link is optional everywhere. 150,120 observations carry no
-- encounter at all (docs/silver-model-findings.md section 4); requiring it
-- would quarantine 6.75% of the largest table for no reason. The patient link
-- is the one that must hold.

-- ---------------------------------------------------------------- observation
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.v_observation AS
SELECT
    o.PATIENT                                AS patient_id,
    NULLIF(o.ENCOUNTER, '')                  AS encounter_id,
    d.code_key,
    o.CODE                                   AS source_code,
    o.DESCRIPTION                            AS source_description,
    o.CATEGORY                               AS category,
    TRY_CAST(o.DATE AS TIMESTAMP)            AS observed_at,
    o.VALUE                                  AS value_text,
    TRY_CAST(o.VALUE AS DOUBLE)              AS value_number,
    o.UNITS                                  AS units,
    o.TYPE                                   AS value_type,
    o._source_file, o._ingested_at, o._batch_id,
    filter(array(
        CASE WHEN p.patient_id IS NULL THEN 'patient_not_found' END,
        CASE WHEN d.code_key IS NULL THEN 'code_not_in_dim_code' END,
        CASE WHEN TRY_CAST(o.DATE AS TIMESTAMP) IS NULL THEN 'date_unparseable' END,
        CASE WHEN o.TYPE = 'numeric' AND TRY_CAST(o.VALUE AS DOUBLE) IS NULL
             THEN 'numeric_value_not_numeric' END
    ), x -> x IS NOT NULL)                   AS violations
FROM ${catalog}.bronze.br_observations o
LEFT JOIN ${catalog}.silver.patient p ON o.PATIENT = p.patient_id
LEFT JOIN ${catalog}.silver.dim_code d ON d.system = 'LOINC' AND d.code = o.CODE;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.observation
(CONSTRAINT valid_observation EXPECT (size(violations) = 0) ON VIOLATION DROP ROW)
COMMENT "Labs and vitals, LOINC. The volume driver."
TBLPROPERTIES ("quality" = "silver")
AS SELECT * FROM ${catalog}.silver.v_observation;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.ops.quarantine_observation
AS SELECT * FROM ${catalog}.silver.v_observation WHERE size(violations) > 0;


-- ----------------------------------------------------------------- medication
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.v_medication AS
SELECT
    m.PATIENT                                 AS patient_id,
    NULLIF(m.ENCOUNTER, '')                   AS encounter_id,
    NULLIF(m.PAYER, '')                       AS payer_id,
    d.code_key,
    m.CODE                                    AS source_code,
    m.DESCRIPTION                             AS source_description,
    TRY_CAST(m.START AS TIMESTAMP)            AS started_at,
    TRY_CAST(NULLIF(m.STOP, '') AS TIMESTAMP) AS stopped_at,
    TRY_CAST(m.BASE_COST AS DOUBLE)           AS base_cost,
    TRY_CAST(m.PAYER_COVERAGE AS DOUBLE)      AS payer_coverage,
    TRY_CAST(m.DISPENSES AS INT)              AS dispenses,
    TRY_CAST(m.TOTALCOST AS DOUBLE)           AS total_cost,
    r.code_key                                AS reason_code_key,
    m._source_file, m._ingested_at, m._batch_id,
    filter(array(
        CASE WHEN p.patient_id IS NULL THEN 'patient_not_found' END,
        CASE WHEN d.code_key IS NULL THEN 'code_not_in_dim_code' END,
        CASE WHEN TRY_CAST(m.START AS TIMESTAMP) IS NULL THEN 'start_unparseable' END,
        CASE WHEN TRY_CAST(NULLIF(m.STOP, '') AS TIMESTAMP) < TRY_CAST(m.START AS TIMESTAMP)
             THEN 'stop_before_start' END
    ), x -> x IS NOT NULL)                    AS violations
FROM ${catalog}.bronze.br_medications m
LEFT JOIN ${catalog}.silver.patient p ON m.PATIENT = p.patient_id
LEFT JOIN ${catalog}.silver.dim_code d ON d.system = 'RxNorm' AND d.code = m.CODE
LEFT JOIN ${catalog}.silver.dim_code r ON r.system = 'SNOMED' AND r.code = m.REASONCODE;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.medication
(CONSTRAINT valid_medication EXPECT (size(violations) = 0) ON VIOLATION DROP ROW)
COMMENT "Prescriptions, RxNorm, with cost and payer coverage."
TBLPROPERTIES ("quality" = "silver")
AS SELECT * FROM ${catalog}.silver.v_medication;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.ops.quarantine_medication
AS SELECT * FROM ${catalog}.silver.v_medication WHERE size(violations) > 0;


-- ------------------------------------------------------------------ procedure
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.v_procedure AS
SELECT
    pr.PATIENT                                 AS patient_id,
    NULLIF(pr.ENCOUNTER, '')                   AS encounter_id,
    d.code_key,
    pr.CODE                                    AS source_code,
    pr.DESCRIPTION                             AS source_description,
    TRY_CAST(pr.START AS TIMESTAMP)            AS started_at,
    TRY_CAST(NULLIF(pr.STOP, '') AS TIMESTAMP) AS stopped_at,
    TRY_CAST(pr.BASE_COST AS DOUBLE)           AS base_cost,
    r.code_key                                 AS reason_code_key,
    pr._source_file, pr._ingested_at, pr._batch_id,
    filter(array(
        CASE WHEN p.patient_id IS NULL THEN 'patient_not_found' END,
        CASE WHEN d.code_key IS NULL THEN 'code_not_in_dim_code' END,
        CASE WHEN TRY_CAST(pr.START AS TIMESTAMP) IS NULL THEN 'start_unparseable' END
    ), x -> x IS NOT NULL)                     AS violations
FROM ${catalog}.bronze.br_procedures pr
LEFT JOIN ${catalog}.silver.patient p ON pr.PATIENT = p.patient_id
LEFT JOIN ${catalog}.silver.dim_code d ON d.system = 'SNOMED' AND d.code = pr.CODE
LEFT JOIN ${catalog}.silver.dim_code r ON r.system = 'SNOMED' AND r.code = pr.REASONCODE;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.procedure
(CONSTRAINT valid_procedure EXPECT (size(violations) = 0) ON VIOLATION DROP ROW)
COMMENT "Procedures, SNOMED, with base cost."
TBLPROPERTIES ("quality" = "silver")
AS SELECT * FROM ${catalog}.silver.v_procedure;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.ops.quarantine_procedure
AS SELECT * FROM ${catalog}.silver.v_procedure WHERE size(violations) > 0;


-- --------------------------------------------------------------- immunization
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.v_immunization AS
SELECT
    i.PATIENT                        AS patient_id,
    NULLIF(i.ENCOUNTER, '')          AS encounter_id,
    d.code_key,
    i.CODE                           AS source_code,
    i.DESCRIPTION                    AS source_description,
    TRY_CAST(i.DATE AS TIMESTAMP)    AS administered_at,
    TRY_CAST(i.BASE_COST AS DOUBLE)  AS base_cost,
    i._source_file, i._ingested_at, i._batch_id,
    filter(array(
        CASE WHEN p.patient_id IS NULL THEN 'patient_not_found' END,
        CASE WHEN d.code_key IS NULL THEN 'code_not_in_dim_code' END,
        CASE WHEN TRY_CAST(i.DATE AS TIMESTAMP) IS NULL THEN 'date_unparseable' END
    ), x -> x IS NOT NULL)           AS violations
FROM ${catalog}.bronze.br_immunizations i
LEFT JOIN ${catalog}.silver.patient p ON i.PATIENT = p.patient_id
LEFT JOIN ${catalog}.silver.dim_code d ON d.system = 'CVX' AND d.code = i.CODE;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.immunization
(CONSTRAINT valid_immunization EXPECT (size(violations) = 0) ON VIOLATION DROP ROW)
COMMENT "Vaccines, CVX."
TBLPROPERTIES ("quality" = "silver")
AS SELECT * FROM ${catalog}.silver.v_immunization;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.ops.quarantine_immunization
AS SELECT * FROM ${catalog}.silver.v_immunization WHERE size(violations) > 0;


-- -------------------------------------------------------------------- allergy
-- The only fact table whose codes span two vocabularies: 916 SNOMED rows and
-- 102 RxNorm. The join must use each row's own SYSTEM, normalised the same way
-- dim_code normalises it. Assuming one system here would misfile 102 rows.
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.v_allergy AS
SELECT
    a.PATIENT                                 AS patient_id,
    NULLIF(a.ENCOUNTER, '')                   AS encounter_id,
    d.code_key,
    a.CODE                                    AS source_code,
    a.DESCRIPTION                             AS source_description,
    CASE WHEN a.SYSTEM IN ('http://snomed.info/sct', 'SNOMED-CT')
         THEN 'SNOMED' ELSE a.SYSTEM END      AS code_system,
    TRY_CAST(a.START AS DATE)                 AS onset_date,
    TRY_CAST(NULLIF(a.STOP, '') AS DATE)      AS resolved_date,
    a.TYPE                                    AS allergy_type,
    a.CATEGORY                                AS category,
    a.SEVERITY1                               AS severity,
    a.DESCRIPTION1                            AS reaction_description,
    a._source_file, a._ingested_at, a._batch_id,
    filter(array(
        CASE WHEN p.patient_id IS NULL THEN 'patient_not_found' END,
        CASE WHEN d.code_key IS NULL THEN 'code_not_in_dim_code' END,
        CASE WHEN TRY_CAST(a.START AS DATE) IS NULL THEN 'onset_unparseable' END
    ), x -> x IS NOT NULL)                    AS violations
FROM ${catalog}.bronze.br_allergies a
LEFT JOIN ${catalog}.silver.patient p ON a.PATIENT = p.patient_id
LEFT JOIN ${catalog}.silver.dim_code d
       ON d.code = a.CODE
      AND d.system = CASE WHEN a.SYSTEM IN ('http://snomed.info/sct', 'SNOMED-CT')
                          THEN 'SNOMED' ELSE a.SYSTEM END;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.allergy
(CONSTRAINT valid_allergy EXPECT (size(violations) = 0) ON VIOLATION DROP ROW)
COMMENT "Allergies. Codes span SNOMED and RxNorm within one table."
TBLPROPERTIES ("quality" = "silver")
AS SELECT * FROM ${catalog}.silver.v_allergy;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.ops.quarantine_allergy
AS SELECT * FROM ${catalog}.silver.v_allergy WHERE size(violations) > 0;


-- ------------------------------------------------------------------- careplan
CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.v_careplan AS
SELECT
    cp.Id                                     AS careplan_id,
    cp.PATIENT                                AS patient_id,
    NULLIF(cp.ENCOUNTER, '')                  AS encounter_id,
    d.code_key,
    cp.CODE                                   AS source_code,
    cp.DESCRIPTION                            AS source_description,
    TRY_CAST(cp.START AS DATE)                AS started_on,
    TRY_CAST(NULLIF(cp.STOP, '') AS DATE)     AS stopped_on,
    r.code_key                                AS reason_code_key,
    cp._source_file, cp._ingested_at, cp._batch_id,
    filter(array(
        CASE WHEN p.patient_id IS NULL THEN 'patient_not_found' END,
        CASE WHEN d.code_key IS NULL THEN 'code_not_in_dim_code' END,
        CASE WHEN TRY_CAST(cp.START AS DATE) IS NULL THEN 'start_unparseable' END
    ), x -> x IS NOT NULL)                    AS violations
FROM ${catalog}.bronze.br_careplans cp
LEFT JOIN ${catalog}.silver.patient p ON cp.PATIENT = p.patient_id
LEFT JOIN ${catalog}.silver.dim_code d ON d.system = 'SNOMED' AND d.code = cp.CODE
LEFT JOIN ${catalog}.silver.dim_code r ON r.system = 'SNOMED' AND r.code = cp.REASONCODE;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.careplan
(CONSTRAINT valid_careplan EXPECT (size(violations) = 0) ON VIOLATION DROP ROW)
COMMENT "Care plans, SNOMED."
TBLPROPERTIES ("quality" = "silver")
AS SELECT * FROM ${catalog}.silver.v_careplan;

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.ops.quarantine_careplan
AS SELECT * FROM ${catalog}.silver.v_careplan WHERE size(violations) > 0;
