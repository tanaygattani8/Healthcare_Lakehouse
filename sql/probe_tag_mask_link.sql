-- Follow-up to probe_governance.sql. Self-contained: builds its own tagged and
-- masked table, tests the drift check in BOTH directions, and drops everything.
--
-- The first version of this file assumed probe_governance.sql's objects were
-- still there. They had been dropped, so it queried an empty catalog and
-- returned zero rows for every probe — which reads identically to a pass.

CREATE TABLE healthcare_dev.ops.probe_link (ssn STRING, city STRING);
CREATE OR REPLACE FUNCTION healthcare_dev.ops.probe_hide(v STRING) RETURN '***';
ALTER TABLE healthcare_dev.ops.probe_link ALTER COLUMN ssn SET MASK healthcare_dev.ops.probe_hide;
ALTER TABLE healthcare_dev.ops.probe_link ALTER COLUMN ssn  SET TAGS ('phi_category' = 'ssn');
ALTER TABLE healthcare_dev.ops.probe_link ALTER COLUMN city SET TAGS ('phi_category' = 'geography');

-- P7: is an applied mask visible as metadata? Expect exactly one row, ssn.
SELECT table_name, column_name, mask_name FROM healthcare_dev.information_schema.column_masks;

-- P8: the drift check. `city` is tagged PHI and deliberately unmasked, so a
-- working check returns exactly one row — city. Returning nothing would mean
-- the join is broken, not that the catalog is clean.
SELECT t.table_name, t.column_name, t.tag_value
FROM healthcare_dev.information_schema.column_tags t
LEFT JOIN healthcare_dev.information_schema.column_masks m
       ON t.table_name  = m.table_name
      AND t.column_name = m.column_name
WHERE t.tag_name = 'phi_category'
  AND m.column_name IS NULL;

-- P9: what does an ABAC policy actually take? Reading the shape beats guessing
-- CREATE POLICY syntax and reporting the syntax error as "unsupported".
DESCRIBE healthcare_dev.information_schema.abac_policy_definitions;

ALTER TABLE healthcare_dev.ops.probe_link ALTER COLUMN ssn DROP MASK;
DROP TABLE healthcare_dev.ops.probe_link;
DROP FUNCTION healthcare_dev.ops.probe_hide;
