-- Phase 5 probes P1 and P3. Kept as a record, like probe_phase4.sql.

-- P1. Can Free Edition create and query a metric view?
CREATE SCHEMA IF NOT EXISTS healthcare_dev.metrics
COMMENT "Phase 5: every business measure defined once, as metric views.";

CREATE OR REPLACE VIEW healthcare_dev.metrics.probe_readmission
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: healthcare_dev.gold.readmission_events
dimensions:
  - name: admit_year
    expr: year(admitted_at)
measures:
  - name: index_stays
    expr: count_if(is_index_stay)
  - name: readmitted
    expr: count_if(is_index_stay AND readmitted_30d)
$$;

-- Expected: 1146, 201 (decision.md D58).
SELECT MEASURE(index_stays) AS index_stays, MEASURE(readmitted) AS readmitted
FROM healthcare_dev.metrics.probe_readmission;

DROP VIEW healthcare_dev.metrics.probe_readmission;

-- P3. Is the billing table readable? If yes, it measures what a run costs.
SELECT usage_date, billing_origin_product, sku_name,
       round(sum(usage_quantity), 3) AS dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - 1
GROUP BY ALL ORDER BY usage_date, dbus DESC;
