-- Phase 3a — the audit view: who read PHI, and when.
--
-- Source is system.query.history rather than system.access.audit. Both exist
-- here (decision.md D41), but access.audit records catalog operations like
-- getTableById, which answers "was this object resolved" rather than "did a
-- person read this data". query.history carries the statement text and the
-- user who ran it.
--
-- The PHI table list is derived from column_tags rather than hardcoded, so
-- tagging a new table adds it to the audit automatically and nothing has to
-- be kept in step by hand.
--
-- ponytail: matches statement text by table name. Two known ceilings, both
-- worth knowing before quoting a number from this view:
--   * a query reading silver.patient through another view is not matched
--   * 'patient' is a substring of 'quarantine_patient', so a read of either
--     matches both rows. Counts here are an upper bound, not a census.
-- The structured alternative is access.audit's request_params, which is
-- precise and far less legible. Revisit if this view is ever used for
-- anything beyond demonstrating that auditing exists.

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
