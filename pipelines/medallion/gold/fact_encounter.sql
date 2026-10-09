-- One row per visit; money as DECIMAL so every engine totals it the same.

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.fact_encounter (
    -- NULL conditions are violations (E57), so allowed NULLs are spelled out.
    CONSTRAINT duration_not_negative EXPECT (duration_hours IS NULL OR duration_hours >= 0) ON VIOLATION FAIL UPDATE,
    -- patient_paid is total minus coverage: negative means an insurer paid more than the bill.
    CONSTRAINT coverage_not_above_bill EXPECT (patient_paid IS NULL OR patient_paid >= 0) ON VIOLATION FAIL UPDATE
)
COMMENT "One row per visit. Money in DECIMAL so totals add up the same in any engine."
TBLPROPERTIES ("quality" = "gold")
AS
SELECT e.encounter_id,
       e.patient_id,
       -- Chicago days, as everywhere else in gold (D81, E74).
       cast(date_format(from_utc_timestamp(e.started_at, 'America/Chicago'), 'yyyyMMdd') AS INT)
                                                           AS start_date_key,
       cast(date_format(from_utc_timestamp(e.stopped_at, 'America/Chicago'), 'yyyyMMdd') AS INT)
                                                           AS stop_date_key,
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
