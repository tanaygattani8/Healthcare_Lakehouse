-- One row per visit, with its dates as keys into dim_date and its money as
-- DECIMAL. Doubles added in a different order give a different last digit;
-- decimals do not, so any engine totals these the same (phase 4, track B).

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.fact_encounter
COMMENT "One row per visit. Money in DECIMAL so totals add up the same in any engine."
TBLPROPERTIES ("quality" = "gold")
AS
SELECT e.encounter_id,
       e.patient_id,
       cast(date_format(e.started_at, 'yyyyMMdd') AS INT)  AS start_date_key,
       cast(date_format(e.stopped_at, 'yyyyMMdd') AS INT)  AS stop_date_key,
       e.started_at,
       e.stopped_at,
       round((unix_timestamp(e.stopped_at) - unix_timestamp(e.started_at)) / 3600.0, 2)
                                                           AS duration_hours,
       e.encounter_class,
       e.canonical_class,
       e.readmission_role,
       e.organization_id,
       e.provider_id,
       e.payer_id,
       e.reason_code_key,
       cast(e.base_cost        AS DECIMAL(14, 2))          AS base_cost,
       cast(e.total_claim_cost AS DECIMAL(14, 2))          AS total_claim_cost,
       cast(e.payer_coverage   AS DECIMAL(14, 2))          AS payer_coverage,
       -- Subtract the rounded amounts, so paid + covered = total on every row.
       cast(e.total_claim_cost AS DECIMAL(14, 2))
         - cast(e.payer_coverage AS DECIMAL(14, 2))        AS patient_paid
FROM ${catalog}.silver.encounter e;
