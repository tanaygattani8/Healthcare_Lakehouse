-- The exact "before" for readmission_signals, for an EXCEPT ALL proof
-- (archive/sql/phase7_proof.sql). Dropped by archive/sql/phase7_cleanup.sql.
CREATE OR REPLACE TABLE healthcare_dev.ops.signals_before AS
SELECT * FROM healthcare_dev.gold.readmission_signals;

SELECT count(*) AS rows FROM healthcare_dev.ops.signals_before;