-- Phase 3a drift check: run after every full refresh or tag/policy change.
-- CHECK 1: a tag value with no policy in its schema (column_masks is empty under ABAC).
-- ponytail: matches the policy text for the quoted tag; fine while no policy has WHEN or principals.

-- A left join: the correlated NOT EXISTS fails with UNRESOLVED_COLUMN.
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

-- CHECK 2: tag census; expect 19 on patient tables, 1 on notes/span tables, else re-run the governance files.

SELECT schema_name, table_name, count(*) AS tagged_columns
FROM healthcare_dev.information_schema.column_tags
WHERE tag_name = 'phi_category'
GROUP BY schema_name, table_name
ORDER BY schema_name;

-- CHECK 3: a PHI column with no tag anywhere; expect no rows (D79).
-- Business addresses aren't PHI; backing tables are skipped, a known limit (D49, D79).
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
