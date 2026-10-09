-- Phase 3a, Task 1 step 7 — the drift check. Run after every pipeline full
-- refresh, and after any change to tags or policies.
--
-- Why this is not the check D42 validated. That one joined column_tags to
-- information_schema.column_masks, which is correct only for a mask attached
-- with ALTER COLUMN ... SET MASK. Under ABAC the mask comes from a policy and
-- column_masks stays empty, so the old check would report all 19 columns
-- unprotected, permanently. A check that always fails gets ignored, which is
-- worse than not having one.
--
-- CHECK 1 — a tag value in use with no policy covering it in that schema.
-- This is the failure that matters: the column is classified as PHI and
-- nothing masks it, and no error is raised anywhere.
--
-- ponytail: matches the policy's condition as text, looking for the quoted
-- tag value. It cannot parse a WHEN clause or a policy restricted by
-- principal. Good enough while every policy here is TO `account users` with no
-- WHEN — revisit if that stops being true.

-- A left join rather than NOT EXISTS: the correlated form cannot see the outer
-- alias here and fails with UNRESOLVED_COLUMN.
SELECT DISTINCT
       t.schema_name,
       t.tag_value,
       'TAGGED BUT NO POLICY' AS problem
FROM healthcare_dev.information_schema.column_tags t
LEFT JOIN healthcare_dev.information_schema.abac_policy_definitions p
       ON p.schema_name = t.schema_name
      AND p.policy_type = 'COLUMN_MASK'
      AND array_join(p.match_columns, ' ') LIKE concat('%''', t.tag_value, '''%')
WHERE t.tag_name = 'phi_category'
  AND p.policy_name IS NULL;

-- CHECK 2 — the tag census. A Lakeflow full refresh recreates the
-- materialized view, and if it drops the column tags the policies stop
-- matching and every masked column silently returns real values. Expect
-- silver.patient = 19, ops.quarantine_patient = 19, bronze.br_patients = 19,
-- and 1 each on bronze.br_notes, silver.phi_span, ops.detection_span and
-- ops.llm_reply (phase 3b). Anything lower means re-run governance_tags.sql,
-- governance_quarantine.sql, governance_bronze.sql and governance_notes.sql.

SELECT schema_name, table_name, count(*) AS tagged_columns
FROM healthcare_dev.information_schema.column_tags
WHERE tag_name = 'phi_category'
GROUP BY schema_name, table_name
ORDER BY schema_name;

-- CHECK 3 — a PHI column with no tag, anywhere in the catalog. CHECKs 1 and 2
-- only see columns someone tagged; a copy nobody tagged is invisible to them.
-- That is how silver.v_patient and bronze.br_patients sat unmasked beside the
-- masked table for six phases (D79). Expect no rows.
--
-- It matches on the identifier columns' names, raw (bronze) and typed
-- (silver), not on a pattern, so a renamed copy would slip past; every copy
-- here keeps Synthea's names. Hospitals, providers and payers carry an
-- ADDRESS, CITY and ZIP too, but a business address is not PHI.
--
-- Backing tables are skipped, and that is a limit, not a pass. Lakeflow keeps
-- each pipeline table's rows in a MANAGED __materialization_mat_<pipeline>_
-- <name>_<n> table in the same schema. Its owner reads it unmasked and
-- unfiltered: tagged, it still returned real SSNs, because schema policies
-- do not apply to it (measured, D79). Tags cannot fix it, so listing it here
-- would only make a check that always fails. Another principal would be
-- granted the table, not its backing table; on this one-account workspace
-- nothing stops the owner (D49).
SELECT c.table_schema, c.table_name, c.column_name, 'PHI COLUMN WITH NO TAG' AS problem
FROM healthcare_dev.information_schema.columns c
LEFT JOIN healthcare_dev.information_schema.column_tags t
       ON t.schema_name = c.table_schema AND t.table_name = c.table_name
      AND t.column_name = c.column_name AND t.tag_name = 'phi_category'
WHERE upper(c.column_name) IN (
        'SSN', 'DRIVERS', 'PASSPORT', 'PREFIX', 'FIRST', 'MIDDLE', 'LAST', 'SUFFIX',
        'MAIDEN', 'ADDRESS', 'CITY', 'COUNTY', 'FIPS', 'BIRTHPLACE', 'ZIP', 'LAT', 'LON',
        'LATITUDE', 'LONGITUDE', 'BIRTHDATE', 'DEATHDATE', 'BIRTH_DATE', 'DEATH_DATE')
  AND c.table_schema <> 'information_schema'
  AND c.table_name NOT RLIKE '(br_organizations|br_providers|br_payers|dim_organization)(_[0-9]+)?$'
  AND c.table_name NOT LIKE '\_\_materialization\_mat\_%'
  AND t.column_name IS NULL
ORDER BY 1, 2, 3;
