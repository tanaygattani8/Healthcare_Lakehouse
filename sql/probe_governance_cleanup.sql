-- Drops everything sql/probe_governance.sql created. The mask must come off
-- the column before its function can be dropped.
ALTER TABLE healthcare_dev.ops.probe_target ALTER COLUMN name DROP MASK;
DROP TABLE IF EXISTS healthcare_dev.ops.probe_target;
DROP TABLE IF EXISTS healthcare_dev.ops.probe_clearance;
DROP FUNCTION IF EXISTS healthcare_dev.ops.probe_mask;
DROP FUNCTION IF EXISTS healthcare_dev.ops.probe_mask2;
