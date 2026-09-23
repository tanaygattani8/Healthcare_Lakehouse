-- Phase 3a, Task 1 step 4 — the column mask policies.
--
-- Attached to the SCHEMA, not to silver.patient. That is the whole point: the
-- pipeline owns the materialized view and recreates it on a full refresh, so a
-- mask attached to the table would be lost silently. A schema policy is not
-- part of the table definition and survives. decision.md D43.
--
-- Four policies, not eight, because MATCH COLUMNS accepts a disjunction:
-- five of the eight tag values share mask_text, and they collapse into one.
--
-- CREATE OR REPLACE rather than DROP + CREATE: DROP POLICY has no IF EXISTS
-- clause, so a re-run of a drop-first file fails on a policy already gone.
--
-- TO `account users` covers everyone, including the identity the pipeline runs
-- as. Gold is built from IDENTIFIED silver on purpose, so building gold while
-- the clearance row is missing fills every gold table with '***' and no error
-- is raised anywhere. The clearance row is the safety catch here, not the mask.

CREATE OR REPLACE POLICY mask_phi_text
  ON SCHEMA healthcare_dev.silver
  COMMENT 'Redact names, addresses and identifier numbers for uncleared readers.'
  COLUMN MASK healthcare_dev.ops.mask_text
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'name')
             OR has_tag_value('phi_category', 'geography')
             OR has_tag_value('phi_category', 'ssn')
             OR has_tag_value('phi_category', 'license')
             OR has_tag_value('phi_category', 'other_id') AS c
  ON COLUMN c;

-- ZIP truncates to three digits rather than redacting, so it needs its own
-- policy even though it is geography.
CREATE OR REPLACE POLICY mask_phi_zip
  ON SCHEMA healthcare_dev.silver
  COMMENT 'Truncate ZIP to the first three digits for uncleared readers.'
  COLUMN MASK healthcare_dev.ops.mask_zip
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'zip') AS c
  ON COLUMN c;

-- Safe Harbor permits the year and nothing finer. The 01-01 that comes back is
-- fabricated, not a real birthday.
CREATE OR REPLACE POLICY mask_phi_date
  ON SCHEMA healthcare_dev.silver
  COMMENT 'Collapse dates to their year for uncleared readers.'
  COLUMN MASK healthcare_dev.ops.mask_date
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'date') AS c
  ON COLUMN c;

-- latitude and longitude are DOUBLE. A mask returns the column's own type, so
-- these cannot go through mask_text.
CREATE OR REPLACE POLICY mask_phi_point
  ON SCHEMA healthcare_dev.silver
  COMMENT 'Null out coordinates for uncleared readers.'
  COLUMN MASK healthcare_dev.ops.mask_point
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'geo_point') AS c
  ON COLUMN c;

SELECT policy_name, on_securable_type, schema_name
FROM healthcare_dev.information_schema.abac_policy_definitions
ORDER BY policy_name;
