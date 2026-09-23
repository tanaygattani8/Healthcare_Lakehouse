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
-- silver = 19 and ops = 19. Anything lower means re-run governance_tags.sql
-- and governance_quarantine.sql.

SELECT schema_name, table_name, count(*) AS tagged_columns
FROM healthcare_dev.information_schema.column_tags
WHERE tag_name = 'phi_category'
GROUP BY schema_name, table_name
ORDER BY schema_name;
