-- One row per (system, code) across every vocabulary; expect 1,340 rows.

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.dim_code
COMMENT "Conformed medical codes. Every clinical fact references code_key."
TBLPROPERTIES ("quality" = "silver")
AS
WITH sourced AS (
    -- SYSTEM stated in the data
    SELECT SYSTEM AS raw_system, CODE AS code, DESCRIPTION AS description, START AS seen_at
    FROM ${catalog}.bronze.br_conditions
    UNION ALL
    SELECT SYSTEM, CODE, DESCRIPTION, START FROM ${catalog}.bronze.br_procedures
    UNION ALL
    SELECT SYSTEM, CODE, DESCRIPTION, START FROM ${catalog}.bronze.br_allergies

    -- SYSTEM absent, so the file determines it
    UNION ALL
    SELECT 'LOINC', CODE, DESCRIPTION, DATE FROM ${catalog}.bronze.br_observations
    UNION ALL
    SELECT 'RxNorm', CODE, DESCRIPTION, START FROM ${catalog}.bronze.br_medications
    UNION ALL
    SELECT 'CVX', CODE, DESCRIPTION, DATE FROM ${catalog}.bronze.br_immunizations
    UNION ALL
    SELECT 'SNOMED', CODE, DESCRIPTION, START FROM ${catalog}.bronze.br_careplans

    -- Encounter type codes, mostly found in no other file.
    UNION ALL
    SELECT 'SNOMED', CODE, DESCRIPTION, START FROM ${catalog}.bronze.br_encounters

    -- Reason codes, or careplan rows would fail their lookup.
    UNION ALL
    SELECT 'SNOMED', REASONCODE, REASONDESCRIPTION, START FROM ${catalog}.bronze.br_encounters
    UNION ALL
    SELECT 'SNOMED', REASONCODE, REASONDESCRIPTION, START FROM ${catalog}.bronze.br_procedures
    UNION ALL
    SELECT 'SNOMED', REASONCODE, REASONDESCRIPTION, START FROM ${catalog}.bronze.br_medications
    UNION ALL
    SELECT 'SNOMED', REASONCODE, REASONDESCRIPTION, START FROM ${catalog}.bronze.br_careplans
),

normalised AS (
    SELECT
        -- Normalise the URI and the short name into one SNOMED system.
        CASE
            WHEN raw_system IN ('http://snomed.info/sct', 'SNOMED-CT') THEN 'SNOMED'
            ELSE raw_system
        END AS system,
        code,
        description,
        TRY_CAST(seen_at AS TIMESTAMP) AS seen_at
    FROM sourced
    WHERE code IS NOT NULL AND code <> ''
),

spans AS (
    SELECT system, code, min(seen_at) AS first_seen, max(seen_at) AS last_seen
    FROM normalised
    GROUP BY system, code
),

-- Latest description wins.
latest AS (
    SELECT system, code, description
    FROM (
        SELECT
            system,
            code,
            description,
            row_number() OVER (
                PARTITION BY system, code
                ORDER BY seen_at DESC NULLS LAST, description
            ) AS rn
        FROM normalised
    )
    WHERE rn = 1
)

SELECT
    -- Deterministic key, so a rebuild orphans no fact row.
    xxhash64(s.system, s.code) AS code_key,
    s.system,
    s.code,
    l.description,
    s.first_seen,
    s.last_seen
FROM spans s
JOIN latest l ON s.system = l.system AND s.code = l.code
