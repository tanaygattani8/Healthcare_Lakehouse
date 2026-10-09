-- The first fact table, verified before the other six copied its shape (E17).

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.v_condition AS
SELECT
    c.PATIENT                              AS patient_id,
    NULLIF(c.ENCOUNTER, '')                AS encounter_id,
    d.code_key,
    c.CODE                                 AS source_code,
    c.DESCRIPTION                          AS source_description,
    TRY_CAST(c.START AS DATE)              AS onset_date,
    TRY_CAST(NULLIF(c.STOP, '') AS DATE)   AS resolved_date,

    c._source_file, c._ingested_at, c._batch_id,

    filter(array(
        CASE WHEN p.patient_id IS NULL THEN 'patient_not_found' END,
        CASE WHEN d.code_key IS NULL THEN 'code_not_in_dim_code' END,
        CASE WHEN TRY_CAST(c.START AS DATE) IS NULL THEN 'onset_unparseable' END,
        CASE WHEN TRY_CAST(NULLIF(c.STOP, '') AS DATE) < TRY_CAST(c.START AS DATE)
             THEN 'resolved_before_onset' END
        -- encounter_id may not resolve: the visit link is optional, the patient link must hold.
    ), x -> x IS NOT NULL)                 AS violations
FROM ${catalog}.bronze.br_conditions c
LEFT JOIN ${catalog}.silver.patient p
       ON c.PATIENT = p.patient_id
LEFT JOIN ${catalog}.silver.dim_code d
       ON d.system = 'SNOMED' AND d.code = c.CODE;


CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.condition
(
    CONSTRAINT valid_condition EXPECT (size(violations) = 0) ON VIOLATION DROP ROW
)
COMMENT "Patient conditions, SNOMED, resolved to dim_code."
TBLPROPERTIES ("quality" = "silver")
AS SELECT * FROM ${catalog}.silver.v_condition;


CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.ops.quarantine_condition
COMMENT "Conditions that failed a rule. Kept whole, never discarded."
AS SELECT * FROM ${catalog}.silver.v_condition WHERE size(violations) > 0;
