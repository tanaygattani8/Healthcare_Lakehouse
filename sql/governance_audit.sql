-- Phase 3a audit view: who read PHI and when, from query.history (D41); PHI tables from column_tags.
-- ponytail: matches statement text, so views are missed and counts are an upper bound.

CREATE OR REPLACE VIEW healthcare_dev.ops.phi_access_audit
COMMENT 'Statements that referenced a PHI-tagged table. Upper bound: matches on statement text.'
AS
WITH phi_tables AS (
    SELECT DISTINCT schema_name, table_name
    FROM healthcare_dev.information_schema.column_tags
    WHERE tag_name = 'phi_category'
)
SELECT h.start_time,
       h.executed_by,
       h.statement_type,
       p.schema_name,
       p.table_name,
       h.execution_status,
       h.statement_id,
       left(h.statement_text, 200) AS statement_preview
FROM system.query.history h
JOIN phi_tables p
  ON h.statement_text ILIKE concat('%', p.table_name, '%')
WHERE h.statement_text IS NOT NULL;

SELECT start_time, executed_by, statement_type, schema_name, table_name
FROM healthcare_dev.ops.phi_access_audit
ORDER BY start_time DESC
LIMIT 5;
