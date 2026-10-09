-- D79: bronze.br_patients under silver's tags, one mask_text policy for every value; re-runnable.

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
