-- Drops phase 7's "before" copy of readmission_signals once the final
-- proof (sql/phase7_proof.sql) read 0.
DROP TABLE IF EXISTS healthcare_dev.ops.signals_before;
