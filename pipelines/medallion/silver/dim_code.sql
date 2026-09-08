-- One row per (system, code) across every vocabulary in the dataset.
-- Six source paths, four systems: allergies carries both SNOMED and RxNorm,
-- and procedures contributes 380 SNOMED codes that overlap conditions by zero.
-- Measured in docs/silver-model-findings.md. Expected: 1,246 rows.

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
),

normalised AS (
    SELECT
        -- conditions and procedures say the URI, allergies says the short name.
        -- Unnormalised, SNOMED becomes two unrelated systems.
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

-- Codes with two descriptions exist today (6299-2, 312961, 133 and others).
-- Latest wins: the most recently seen description is the current one.
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
    -- Deterministic: the same code yields the same key on every rebuild, so
    -- silver can be dropped and rebuilt from bronze without orphaning every
    -- fact row. A counter cannot promise that.
    xxhash64(s.system, s.code) AS code_key,
    s.system,
    s.code,
    l.description,
    s.first_seen,
    s.last_seen
FROM spans s
JOIN latest l ON s.system = l.system AND s.code = l.code
