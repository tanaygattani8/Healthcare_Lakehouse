-- Row count and a hash sum for every gold table. Two runs that match mean
-- the same rows, whatever their order. The cast matters: a plain sum of
-- 64-bit hashes overflows, and with ANSI mode the warehouse raises an error.
-- key_copies (a gate column, E59) is left out, so runs from before and after
-- it was added compare. Kept after phase 7: rerun it to show a change left
-- gold untouched.
SELECT 'care_gap' AS t, count(*) AS rows, sum(cast(xxhash64(* EXCEPT (key_copies)) AS DECIMAL(38, 0))) AS fingerprint FROM healthcare_dev.gold.care_gap
UNION ALL SELECT 'dim_date', count(*), sum(cast(xxhash64(*) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.dim_date
UNION ALL SELECT 'dim_organization', count(*), sum(cast(xxhash64(*) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.dim_organization
UNION ALL SELECT 'dim_payer', count(*), sum(cast(xxhash64(*) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.dim_payer
UNION ALL SELECT 'dim_provider', count(*), sum(cast(xxhash64(*) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.dim_provider
UNION ALL SELECT 'fact_encounter', count(*), sum(cast(xxhash64(*) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.fact_encounter
UNION ALL SELECT 'measure_code', count(*), sum(cast(xxhash64(*) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.measure_code
UNION ALL SELECT 'patient_360', count(*), sum(cast(xxhash64(*) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.patient_360
UNION ALL SELECT 'planned_procedure', count(*), sum(cast(xxhash64(*) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.planned_procedure
UNION ALL SELECT 'planned_reason', count(*), sum(cast(xxhash64(*) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.planned_reason
UNION ALL SELECT 'readmission_events', count(*), sum(cast(xxhash64(* EXCEPT (key_copies)) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.readmission_events
UNION ALL SELECT 'readmission_signals', count(*), sum(cast(xxhash64(* EXCEPT (key_copies)) AS DECIMAL(38, 0))) FROM healthcare_dev.gold.readmission_signals
ORDER BY t;