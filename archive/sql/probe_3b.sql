-- Phase 3b, Task 0 — what the platform offers before anything is planned
-- around it.
--
-- Ordered least-likely-to-fail last-first: run_sql.py stops on the first
-- error, and ai_query is the one most likely to be absent.

-- P4: did anything auto-apply the built-in class.* governed tags?
SELECT count(*) AS auto_classified
FROM healthcare_dev.information_schema.column_tags
WHERE tag_name LIKE 'class.%';

-- P3: is there an MLflow surface to record runs against?
SHOW TABLES IN system.mlflow;

-- P2: what model serving exists at all?
SHOW TABLES IN system.serving;

-- P1: is there a Foundation Model endpoint callable from SQL? This decides
-- whether stage 3 exists.
SELECT ai_query('databricks-meta-llama-3-3-70b-instruct',
                'Reply with the single word OK') AS llm;
