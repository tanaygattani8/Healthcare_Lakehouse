-- Phase 3a, Task 1 step 6 — extend the same governance to quarantine.
--
-- ops.quarantine_patient keeps whole failed rows, on purpose: a dropped row
-- cannot be debugged. But keeping the row is the requirement, not keeping its
-- SSN readable, and a policy on SCHEMA silver does not reach schema ops.
--
-- The policies below are separate objects from the silver ones because a
-- policy is attached to exactly one securable. Same tag vocabulary, same mask
-- functions, so the two stay in step as long as both files are re-run
-- together after a full refresh.
--
-- ops.phi_clearance is deliberately untagged. The mask functions read it, and
-- masking the table that decides who is masked would be circular.

ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN SSN        SET TAGS ('phi_category' = 'ssn');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN DRIVERS    SET TAGS ('phi_category' = 'license');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN PASSPORT   SET TAGS ('phi_category' = 'other_id');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN PREFIX     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN FIRST      SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN MIDDLE     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN LAST       SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN SUFFIX     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN MAIDEN     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN ADDRESS    SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN CITY       SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN COUNTY     SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN FIPS       SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN BIRTHPLACE SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN ZIP        SET TAGS ('phi_category' = 'zip');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN latitude   SET TAGS ('phi_category' = 'geo_point');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN longitude  SET TAGS ('phi_category' = 'geo_point');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN birth_date SET TAGS ('phi_category' = 'date');
ALTER TABLE healthcare_dev.ops.quarantine_patient ALTER COLUMN death_date SET TAGS ('phi_category' = 'date');

CREATE OR REPLACE POLICY mask_phi_text
  ON SCHEMA healthcare_dev.ops
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

CREATE OR REPLACE POLICY mask_phi_zip
  ON SCHEMA healthcare_dev.ops
  COLUMN MASK healthcare_dev.ops.mask_zip
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'zip') AS c
  ON COLUMN c;

CREATE OR REPLACE POLICY mask_phi_date
  ON SCHEMA healthcare_dev.ops
  COLUMN MASK healthcare_dev.ops.mask_date
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'date') AS c
  ON COLUMN c;

CREATE OR REPLACE POLICY mask_phi_point
  ON SCHEMA healthcare_dev.ops
  COLUMN MASK healthcare_dev.ops.mask_point
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'geo_point') AS c
  ON COLUMN c;

SELECT schema_name, policy_name
FROM healthcare_dev.information_schema.abac_policy_definitions
ORDER BY schema_name, policy_name;
