-- Phase 3a, Task 1 step 3 — classify the PHI columns of silver.patient.
--
-- Tags carry no protection on their own. They are what the ABAC policies in
-- step 4 match on, which makes them load-bearing: a lost tag stops the policy
-- matching and the column silently returns real values. Hence the drift check
-- in step 7, and hence re-running this file after any pipeline full refresh.
--
-- Re-runnable. SET TAGS overwrites the value for a key it already holds.
--
-- Two columns are deliberately absent:
--   STATE       Safe Harbor permits state, and the row filter keys off it.
--   patient_id  Masking a join key breaks every downstream join. Safe Harbor
--               does cover it; a surrogate key in the deid branch is 3b's
--               answer, not a mask here.

-- ssn / license / other_id — three different Safe Harbor identifier types that
-- happen to share mask_text.
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN SSN        SET TAGS ('phi_category' = 'ssn');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN DRIVERS    SET TAGS ('phi_category' = 'license');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN PASSPORT   SET TAGS ('phi_category' = 'other_id');

-- name
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN PREFIX     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN FIRST      SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN MIDDLE     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN LAST       SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN SUFFIX     SET TAGS ('phi_category' = 'name');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN MAIDEN     SET TAGS ('phi_category' = 'name');

-- geography, the STRING kind
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN ADDRESS    SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN CITY       SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN COUNTY     SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN FIPS       SET TAGS ('phi_category' = 'geography');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN BIRTHPLACE SET TAGS ('phi_category' = 'geography');

-- zip truncates rather than redacting, so it cannot share the value above
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN ZIP        SET TAGS ('phi_category' = 'zip');

-- geo_point exists because these two are DOUBLE and a mask returns the
-- column's own type
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN latitude   SET TAGS ('phi_category' = 'geo_point');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN longitude  SET TAGS ('phi_category' = 'geo_point');

-- date
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN birth_date SET TAGS ('phi_category' = 'date');
ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN death_date SET TAGS ('phi_category' = 'date');

SELECT tag_value, count(*) AS columns
FROM healthcare_dev.information_schema.column_tags
WHERE tag_name = 'phi_category'
GROUP BY tag_value
ORDER BY tag_value;
