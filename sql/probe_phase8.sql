-- Phase 8, step 0 (spec section 1). Read-only, except the throwaway view in
-- probe c, which this file drops again.

-- Probe a: the last day of data, and the last day of its month. Equal
-- means the month is complete. metrics.kpi_window handles both cases.
SELECT to_date(from_utc_timestamp(max(started_at), 'America/Chicago')) AS end_day,
       last_day(to_date(from_utc_timestamp(max(started_at), 'America/Chicago'))) AS month_end
FROM healthcare_dev.gold.fact_encounter;

-- Probe c: a star join in a metric view.
CREATE OR REPLACE VIEW healthcare_dev.metrics.probe_join
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: healthcare_dev.gold.fact_encounter
joins:
  - name: pay
    source: healthcare_dev.gold.dim_payer
    on: source.payer_id = pay.payer_id
dimensions:
  - name: payer
    expr: pay.name
measures:
  - name: visits
    expr: count(*)
$$;

-- Expect payers = the number of rows in dim_payer, and visits_off = 0.
SELECT (SELECT count(*) FROM (SELECT payer, MEASURE(visits) AS v
                              FROM healthcare_dev.metrics.probe_join GROUP BY ALL)) AS payers,
       (SELECT sum(v) FROM (SELECT payer, MEASURE(visits) AS v
                            FROM healthcare_dev.metrics.probe_join GROUP BY ALL))
     - (SELECT count(*) FROM healthcare_dev.gold.fact_encounter) AS visits_off;

DROP VIEW healthcare_dev.metrics.probe_join;
