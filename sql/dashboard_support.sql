-- Phase 8: what the operations dashboard needs besides the metric views.
-- Kept out of sql/metric_views.sql on purpose: the text-to-SQL metrics
-- contestant reads that file as its prompt, and in dev-3 it wrapped answers
-- in shown(), which the SQL safety gate blocks (D74). These are dashboard
-- plumbing, not metrics. Run after sql/metric_views.sql.

-- The dashboard privacy rule (D66, D72, plan P-c): NULL when the group
-- count n is 1-10 or unknown, otherwise value. Every number a dashboard
-- dataset returns goes through this, which hides each small cell in the view
-- the viewer picked. It does not stop one filtered view giving a hidden cell
-- back by subtraction (a hospital table beside the stays tile, say): inside
-- the logged-in dashboard that is accepted (D74). Only the unfiltered view is
-- public, and publish_snapshot checks it for subtraction too (D81).
CREATE OR REPLACE FUNCTION healthcare_dev.metrics.shown(n BIGINT, value DOUBLE)
RETURNS DOUBLE
COMMENT "Phase 8 privacy rule: NULL when the group count n is 1-10 or unknown (D66, D72), else value."
RETURN CASE WHEN n IS NULL OR n BETWEEN 1 AND 10 THEN NULL ELSE value END;

-- The dashboard windows, defined once: the last 12 complete months of data
-- and the 12 before them, as month starts in Chicago time.
CREATE OR REPLACE VIEW healthcare_dev.metrics.kpi_window
COMMENT "Phase 8: the last 12 complete months of data (window_start to last_month) and the 12 before them (prior_start to prior_end). Month starts, Chicago time."
AS
WITH data_end AS (
    SELECT to_date(from_utc_timestamp(max(started_at), 'America/Chicago')) AS end_day
    FROM healthcare_dev.gold.fact_encounter
),
complete AS (
    SELECT CASE WHEN end_day = last_day(end_day) THEN trunc(end_day, 'MM')
                ELSE add_months(trunc(end_day, 'MM'), -1) END AS last_month
    FROM data_end
)
SELECT last_month,
       add_months(last_month, -11) AS window_start,
       add_months(last_month, -23) AS prior_start,
       add_months(last_month, -12) AS prior_end
FROM complete;
