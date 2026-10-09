-- Phase 3a column masks, on the SCHEMA so a full refresh can't drop them (D43); clearance is the catch.

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

-- ZIP truncates rather than redacts, so it has its own policy.
CREATE OR REPLACE POLICY mask_phi_zip
  ON SCHEMA healthcare_dev.silver
  COMMENT 'Truncate ZIP to the first three digits for uncleared readers.'
  COLUMN MASK healthcare_dev.ops.mask_zip
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'zip') AS c
  ON COLUMN c;

-- Year only (Safe Harbor); the 01-01 is fabricated.
CREATE OR REPLACE POLICY mask_phi_date
  ON SCHEMA healthcare_dev.silver
  COMMENT 'Collapse dates to their year for uncleared readers.'
  COLUMN MASK healthcare_dev.ops.mask_date
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'date') AS c
  ON COLUMN c;

-- DOUBLE columns need a DOUBLE mask.
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
