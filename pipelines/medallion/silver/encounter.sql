-- One row per encounter. The spine every clinical fact hangs off.

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.v_encounter AS
SELECT
    e.Id                                          AS encounter_id,
    e.PATIENT                                     AS patient_id,
    TRY_CAST(e.START AS TIMESTAMP)                AS started_at,
    TRY_CAST(e.STOP  AS TIMESTAMP)                AS stopped_at,

    e.ENCOUNTERCLASS                              AS encounter_class,
    m.canonical_class,
    m.readmission_role,

    e.ORGANIZATION                                AS organization_id,
    e.PROVIDER                                    AS provider_id,
    e.PAYER                                       AS payer_id,

    -- The reason for the visit is a SNOMED code, so it joins dim_code like
    -- any other clinical code rather than living here as loose text.
    d.code_key                                    AS reason_code_key,
    e.REASONDESCRIPTION                           AS reason_description,

    TRY_CAST(e.BASE_ENCOUNTER_COST AS DOUBLE)     AS base_cost,
    TRY_CAST(e.TOTAL_CLAIM_COST AS DOUBLE)        AS total_claim_cost,
    TRY_CAST(e.PAYER_COVERAGE AS DOUBLE)          AS payer_coverage,

    e._source_file, e._ingested_at, e._batch_id,

    filter(array(
        CASE WHEN TRY_CAST(e.START AS TIMESTAMP) IS NULL
             THEN 'start_unparseable' END,
        CASE WHEN TRY_CAST(e.STOP AS TIMESTAMP) < TRY_CAST(e.START AS TIMESTAMP)
             THEN 'stop_before_start' END,
        CASE WHEN p.patient_id IS NULL
             THEN 'patient_not_found' END,
        CASE WHEN m.encounter_class IS NULL
             THEN 'encounter_class_unmapped' END
    ), x -> x IS NOT NULL)                        AS violations
FROM ${catalog}.bronze.br_encounters e
LEFT JOIN ${catalog}.silver.patient p
       ON e.PATIENT = p.patient_id
LEFT JOIN ${catalog}.silver.encounter_class_map m
       ON e.ENCOUNTERCLASS = m.encounter_class
LEFT JOIN ${catalog}.silver.dim_code d
       ON d.system = 'SNOMED' AND d.code = e.REASONCODE;


CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.encounter
(
    CONSTRAINT valid_encounter EXPECT (size(violations) = 0) ON VIOLATION DROP ROW
)
COMMENT "One row per encounter. canonical_class and readmission_role from the lookup."
TBLPROPERTIES ("quality" = "silver")
AS SELECT * FROM ${catalog}.silver.v_encounter;


CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.ops.quarantine_encounter
COMMENT "Encounters that failed a rule. Kept whole, never discarded."
AS SELECT * FROM ${catalog}.silver.v_encounter WHERE size(violations) > 0;
