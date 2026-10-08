-- D79 — bring bronze.br_patients under the same governance as silver.patient.
--
-- Bronze keeps every identifier as the raw CSV string. Masking only the silver
-- copy left this one readable by anyone who can read bronze, which the audit
-- found and governance_check.sql CHECK 3 now catches.
--
-- Same tag values as silver, so the census and CHECK 1 compare like with like.
-- One policy, not four: every bronze column is a STRING, so mask_text fits all
-- eight values and returns '***'. Silver's year-keeping date mask and ZIP
-- truncation need typed columns; nothing should read bronze but the pipeline.
--
-- The pipeline reads this table to build silver. It runs as a cleared user, so
-- it sees real values. Without the clearance row every birth date reads '***',
-- fails TRY_CAST, and every patient lands in ops.quarantine_patient: the D47
-- hazard, but now loud rather than silent.
--
-- Re-runnable. Replaces governance_notes.sql's bronze policy, which matched
-- only the five text values.

ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN SSN        SET TAGS ('phi_category' = 'ssn');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN DRIVERS    SET TAGS ('phi_category' = 'license');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN PASSPORT   SET TAGS ('phi_category' = 'other_id');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN PREFIX     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN FIRST      SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN MIDDLE     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN LAST       SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN SUFFIX     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN MAIDEN     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN ADDRESS    SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN CITY       SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN COUNTY     SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN FIPS       SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN BIRTHPLACE SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN ZIP        SET TAGS ('phi_category' = 'zip');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN LAT        SET TAGS ('phi_category' = 'geo_point');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN LON        SET TAGS ('phi_category' = 'geo_point');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN BIRTHDATE  SET TAGS ('phi_category' = 'date');
ALTER TABLE healthcare_dev.bronze.br_patients ALTER COLUMN DEATHDATE  SET TAGS ('phi_category' = 'date');

CREATE OR REPLACE POLICY mask_phi_text
  ON SCHEMA healthcare_dev.bronze
  COMMENT 'Redact every PHI column in bronze for uncleared readers: all raw strings.'
  COLUMN MASK healthcare_dev.ops.mask_text
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'name')
             OR has_tag_value('phi_category', 'geography')
             OR has_tag_value('phi_category', 'ssn')
             OR has_tag_value('phi_category', 'license')
             OR has_tag_value('phi_category', 'other_id')
             OR has_tag_value('phi_category', 'zip')
             OR has_tag_value('phi_category', 'geo_point')
             OR has_tag_value('phi_category', 'date') AS c
  ON COLUMN c;
