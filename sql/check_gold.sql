-- Checks for the gold layer. Grows with each phase 4 step; rerun it whole.

-- Step 1. Every one of these must be 0.
SELECT count_if(o.organization_id IS NULL) AS encounters_with_unknown_organization,
       count_if(p.provider_id IS NULL)     AS encounters_with_unknown_provider,
       count_if(y.payer_id IS NULL)        AS encounters_with_unknown_payer
FROM healthcare_dev.silver.encounter e
LEFT JOIN healthcare_dev.gold.dim_organization o ON o.organization_id = e.organization_id
LEFT JOIN healthcare_dev.gold.dim_provider     p ON p.provider_id     = e.provider_id
LEFT JOIN healthcare_dev.gold.dim_payer        y ON y.payer_id        = e.payer_id;

-- Each reference table has one row per id. Must be 0.
SELECT (SELECT count(*) - count(DISTINCT organization_id) FROM healthcare_dev.gold.dim_organization) AS duplicate_organizations,
       (SELECT count(*) - count(DISTINCT provider_id) FROM healthcare_dev.gold.dim_provider)         AS duplicate_providers,
       (SELECT count(*) - count(DISTINCT payer_id) FROM healthcare_dev.gold.dim_payer)               AS duplicate_payers;

SELECT min(calendar_date), max(calendar_date), count(*) AS days,
       count(*) - count(DISTINCT date_key) AS duplicate_days_must_be_0
FROM healthcare_dev.gold.dim_date;

-- Step 2. Same rows as silver, and the money adds up the same. The two
-- totals may differ by cents (round-then-add vs add-then-round); a dollar is a bug.
SELECT (SELECT count(*) FROM healthcare_dev.gold.fact_encounter)   AS gold_rows,
       (SELECT count(*) FROM healthcare_dev.silver.encounter)      AS silver_rows,
       (SELECT sum(total_claim_cost) FROM healthcare_dev.gold.fact_encounter)  AS gold_total,
       (SELECT round(sum(total_claim_cost), 2) FROM healthcare_dev.silver.encounter) AS silver_total,
       (SELECT count_if(duration_hours < 0) FROM healthcare_dev.gold.fact_encounter)
                                                                    AS negative_durations_must_be_0;

-- Every visit's dates exist in dim_date, and no insurer paid more than the
-- bill (patient_paid is total minus coverage, so that shows as negative). Must be 0.
SELECT count_if(ds.date_key IS NULL)                                   AS start_not_in_dim_date,
       count_if(f.stop_date_key IS NOT NULL AND dt.date_key IS NULL)   AS stop_not_in_dim_date,
       count_if(f.patient_paid < 0)                                    AS coverage_above_bill
FROM healthcare_dev.gold.fact_encounter f
LEFT JOIN healthcare_dev.gold.dim_date ds ON ds.date_key = f.start_date_key
LEFT JOIN healthcare_dev.gold.dim_date dt ON dt.date_key = f.stop_date_key;
