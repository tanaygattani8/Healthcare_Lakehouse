-- Phase 3a row filter on STATE (row_scope tag); all patients are in MA, and a mismatch empties gold silently.

-- scope_state is created by governance_bootstrap.sql (E71).

-- '*' is every state; set before the policy, since NULL hides every row.
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
