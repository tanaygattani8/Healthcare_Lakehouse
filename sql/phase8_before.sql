-- The exact "before" for readmission_signals, in case the fingerprint
-- disagrees after phase 8 moves stay cost into readmission_events (plan
-- P-i). Dropped by sql/phase8_cleanup.sql in Task 8.
CREATE OR REPLACE TABLE healthcare_dev.ops.signals_before AS
SELECT * FROM healthcare_dev.gold.readmission_signals;

SELECT count(*) AS rows FROM healthcare_dev.ops.signals_before;
