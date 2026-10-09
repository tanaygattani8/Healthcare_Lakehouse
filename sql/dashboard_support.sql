-- Phase 8 dashboard plumbing, kept out of metric_views.sql, the text-to-SQL prompt (D74).

-- NULL when n is 1-10 or unknown (D66, D72); subtraction is guarded only in the public view (D74, D81).
CREATE OR REPLACE FUNCTION healthcare_dev.metrics.shown(n BIGINT, value DOUBLE)
RETURNS DOUBLE
COMMENT "Phase 8 privacy rule: NULL when the group count n is 1-10 or unknown (D66, D72), else value."
RETURN CASE WHEN n IS NULL OR n BETWEEN 1 AND 10 THEN NULL ELSE value END;

-- Dashboard windows: last 12 complete months and the 12 before, as Chicago month starts.
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
