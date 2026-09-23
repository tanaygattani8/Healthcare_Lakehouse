-- Phase 3a — row filter, restricting which patients a reader sees at all.
--
-- A separate governed tag from phi_category on purpose. STATE is not PHI —
-- Safe Harbor permits state — so tagging it phi_category would mask it and
-- put it under the wrong policy. row_scope says what a column is for, not
-- what kind of identifier it is.
--
-- HONEST LIMIT: every patient in this dataset is in Massachusetts. This filter
-- can therefore only demonstrate all-rows versus no-rows. It shows the
-- mechanism working; it is not doing useful segregation. A second state would
-- make it real, and nothing about the code would change.
--
-- HAZARD, worse than the column masks: a row filter applies to the identity
-- the pipeline runs as. Building gold while scope_state does not match the
-- data silently produces EMPTY gold tables rather than wrong ones. No error is
-- raised. Check ops.phi_clearance before any gold build.

-- Databricks takes ADD COLUMNS (c TYPE), not ADD COLUMN c TYPE, and there is
-- no IF NOT EXISTS here — so this one statement fails on a re-run. Comment it
-- out once the column exists rather than reaching for a workaround.
-- ALTER TABLE healthcare_dev.ops.phi_clearance ADD COLUMNS (scope_state STRING);

-- '*' means every state. A NULL here would hide every row from this user,
-- which is why the update runs before the policy is created.
UPDATE healthcare_dev.ops.phi_clearance
   SET scope_state = '*'
 WHERE user_email = current_user() AND scope_state IS NULL;

CREATE GOVERNED TAG row_scope
  DESCRIPTION 'Marks a column as a row-visibility scope, not an identifier'
  VALUES ('state');

ALTER TABLE healthcare_dev.silver.patient ALTER COLUMN STATE SET TAGS ('row_scope' = 'state');

CREATE OR REPLACE FUNCTION healthcare_dev.ops.filter_state(s STRING)
RETURNS BOOLEAN
RETURN EXISTS (SELECT 1 FROM healthcare_dev.ops.phi_clearance
                WHERE user_email = current_user()
                  AND (scope_state = '*' OR scope_state = s));

CREATE OR REPLACE POLICY filter_patient_state
  ON SCHEMA healthcare_dev.silver
  COMMENT 'A reader sees only the states their clearance row scopes them to.'
  ROW FILTER healthcare_dev.ops.filter_state
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('row_scope', 'state') AS st
  USING COLUMNS (st);

SELECT policy_name, policy_type, schema_name
FROM healthcare_dev.information_schema.abac_policy_definitions
ORDER BY schema_name, policy_name;
