-- P10-P13: does tag-driven masking (ABAC) work on Free Edition?
--
-- First attempt failed at the policy with `Unknown tag policy key
-- 'phi_category'`. ABAC matches GOVERNED tags — account-level keys with a
-- declared value list — not the free-form ones ALTER ... SET TAGS creates.
-- So the governed tag is registered first.
--
-- Ordered least-likely-to-fail first: run_sql.py stops on the first error, and
-- cleanup is a separate file for that reason.

DROP TABLE IF EXISTS healthcare_dev.ops.probe_abac;
DROP FUNCTION IF EXISTS healthcare_dev.ops.probe_redact;

-- P10: can this account register a governed tag? Account-admin operation.
CREATE GOVERNED TAG phi_category
  DESCRIPTION 'HIPAA Safe Harbor identifier type'
  VALUES ('name', 'ssn', 'date', 'geography', 'contact');

CREATE TABLE healthcare_dev.ops.probe_abac (ssn STRING, city STRING);
INSERT INTO healthcare_dev.ops.probe_abac VALUES ('123-45-6789', 'Boston');
ALTER TABLE healthcare_dev.ops.probe_abac ALTER COLUMN ssn  SET TAGS ('phi_category' = 'ssn');
ALTER TABLE healthcare_dev.ops.probe_abac ALTER COLUMN city SET TAGS ('phi_category' = 'geography');
CREATE OR REPLACE FUNCTION healthcare_dev.ops.probe_redact(v STRING) RETURN '***';

-- Baseline, so a later '***' is attributable to the policy and nothing else.
SELECT ssn, city FROM healthcare_dev.ops.probe_abac;

-- P11: create a COLUMN MASK policy matching on the tag KEY.
CREATE OR REPLACE POLICY probe_mask_all
  ON SCHEMA healthcare_dev.ops
  COMMENT 'probe: mask every column tagged phi_category'
  COLUMN MASK healthcare_dev.ops.probe_redact
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag('phi_category') AS c
  ON COLUMN c;

SELECT policy_name, policy_type, on_securable_type, match_columns
FROM healthcare_dev.information_schema.abac_policy_definitions;

-- Expect BOTH columns masked: key matching cannot tell ssn from geography.
SELECT ssn, city FROM healthcare_dev.ops.probe_abac;

-- P12: match on the tag VALUE instead. This is the one that decides whether
-- 3a needs one policy per Safe Harbor category or a single blunt one.
CREATE OR REPLACE POLICY probe_mask_all
  ON SCHEMA healthcare_dev.ops
  COMMENT 'probe: mask only columns tagged phi_category = ssn'
  COLUMN MASK healthcare_dev.ops.probe_redact
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'ssn') AS c
  ON COLUMN c;

-- Expect ssn masked, city in the clear.
SELECT ssn, city FROM healthcare_dev.ops.probe_abac;
