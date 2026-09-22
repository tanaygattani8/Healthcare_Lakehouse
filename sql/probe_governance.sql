-- P1: can this account create a masking function at all?
CREATE OR REPLACE FUNCTION healthcare_dev.ops.probe_mask(v STRING)
RETURN CASE WHEN is_account_group_member('admins') THEN v ELSE '***' END;

-- P2: can a masking function read a table? (the clearance-table design)
CREATE TABLE IF NOT EXISTS healthcare_dev.ops.probe_clearance
  (user_email STRING, level STRING);
INSERT INTO healthcare_dev.ops.probe_clearance VALUES (current_user(), 'full');

CREATE OR REPLACE FUNCTION healthcare_dev.ops.probe_mask2(v STRING)
RETURN CASE WHEN EXISTS (
    SELECT 1 FROM healthcare_dev.ops.probe_clearance
    WHERE user_email = current_user() AND level = 'full')
  THEN v ELSE '***' END;

-- P3: can a mask be attached, and does it actually mask?
CREATE TABLE healthcare_dev.ops.probe_target (name STRING MASK healthcare_dev.ops.probe_mask2);
INSERT INTO healthcare_dev.ops.probe_target VALUES ('Lucius Emard');
SELECT name FROM healthcare_dev.ops.probe_target;
DELETE FROM healthcare_dev.ops.probe_clearance WHERE user_email = current_user();
SELECT name FROM healthcare_dev.ops.probe_target;

-- P4: do column tags work?
ALTER TABLE healthcare_dev.ops.probe_target
  ALTER COLUMN name SET TAGS ('phi_category' = 'name');
SELECT * FROM healthcare_dev.information_schema.column_tags;

-- P5: do audit system tables exist on Free Edition?
SHOW SCHEMAS IN system;
SELECT * FROM system.access.audit LIMIT 1;