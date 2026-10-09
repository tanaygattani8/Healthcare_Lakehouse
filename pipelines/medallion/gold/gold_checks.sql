-- Cross-table gates (D73): one row of counts, each must be <=> 0 (NULL-safe, E57); fails the update, can't roll back.

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW gold_checks (
    CONSTRAINT unknown_organization EXPECT (unknown_organization <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT unknown_provider EXPECT (unknown_provider <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT unknown_payer EXPECT (unknown_payer <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT duplicate_organization EXPECT (duplicate_organization <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT duplicate_provider EXPECT (duplicate_provider <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT duplicate_payer EXPECT (duplicate_payer <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT duplicate_date EXPECT (duplicate_date <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT start_not_in_dim_date EXPECT (start_not_in_dim_date <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT stop_not_in_dim_date EXPECT (stop_not_in_dim_date <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT fact_rows_off EXPECT (fact_rows_off <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT fact_dollars_off EXPECT (fact_dollars_off <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT patient_360_rows_off EXPECT (patient_360_rows_off <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT patient_360_encounters_off EXPECT (patient_360_encounters_off <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT patient_360_dollars_off EXPECT (patient_360_dollars_off <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT patient_360_readmissions_off EXPECT (patient_360_readmissions_off <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT signals_rows_off EXPECT (signals_rows_off <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT signals_duplicate_keys EXPECT (signals_duplicate_keys <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT nystatin_counted EXPECT (nystatin_counted <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT statin_missed EXPECT (statin_missed <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT surgery_from_previous_stay EXPECT (surgery_from_previous_stay <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT gold_tagged_columns EXPECT (gold_tagged_columns <=> 0) ON VIOLATION FAIL UPDATE,
    CONSTRAINT events_encounters_off EXPECT (events_encounters_off <=> 0) ON VIOLATION FAIL UPDATE
)
COMMENT "Cross-table gates: one row of violation counts, every one must be 0."
AS
WITH fact AS (
    SELECT count(*) AS n, sum(total_claim_cost) AS dollars
    FROM ${catalog}.gold.fact_encounter
),
silver_encounter AS (
    SELECT count(*) AS n, round(sum(total_claim_cost), 2) AS dollars
    FROM ${catalog}.silver.encounter
),
unknown AS (
    SELECT count_if(o.organization_id IS NULL) AS unknown_organization,
           count_if(p.provider_id IS NULL)     AS unknown_provider,
           count_if(y.payer_id IS NULL)        AS unknown_payer
    FROM ${catalog}.silver.encounter e
    LEFT JOIN ${catalog}.gold.dim_organization o ON o.organization_id = e.organization_id
    LEFT JOIN ${catalog}.gold.dim_provider     p ON p.provider_id     = e.provider_id
    LEFT JOIN ${catalog}.gold.dim_payer        y ON y.payer_id        = e.payer_id
),
dates AS (
    SELECT count_if(ds.date_key IS NULL)                                 AS start_not_in_dim_date,
           count_if(f.stop_date_key IS NOT NULL AND dt.date_key IS NULL) AS stop_not_in_dim_date
    FROM ${catalog}.gold.fact_encounter f
    LEFT JOIN ${catalog}.gold.dim_date ds ON ds.date_key = f.start_date_key
    LEFT JOIN ${catalog}.gold.dim_date dt ON dt.date_key = f.stop_date_key
),
p360 AS (
    SELECT count(*) AS n, count(DISTINCT patient_id) AS patients,
           sum(encounters) AS encounters, sum(total_claim_cost) AS dollars,
           sum(readmissions_30d) AS readmissions
    FROM ${catalog}.gold.patient_360
),
events AS (
    SELECT count_if(is_index_stay)                    AS index_stays,
           count_if(is_index_stay AND readmitted_30d) AS readmitted,
           sum(encounters_in_stay)                    AS encounters
    FROM ${catalog}.gold.readmission_events
),
signals AS (
    SELECT count(*) AS n, count(DISTINCT patient_id, stay_no) AS keys
    FROM ${catalog}.gold.readmission_signals
),
-- The statin rule both ways (D57): a statin brand missing from measure_code fails here.
statin AS (
    SELECT count_if(lower(m.source_description) LIKE '%nystatin%' AND hit.code IS NOT NULL)
                                                                       AS nystatin_counted,
           count_if(lower(m.source_description) NOT LIKE '%nystatin%' AND hit.code IS NULL)
                                                                       AS statin_missed
    FROM ${catalog}.silver.medication m
    LEFT JOIN ${catalog}.gold.measure_code hit
      ON hit.measure = 'statin_therapy' AND hit.role = 'numerator'
     AND lower(m.source_description) RLIKE concat('\\b', hit.code, '\\b')
    WHERE lower(m.source_description) LIKE '%statin%'
),
-- D68's window starts the day before admission: no heart operation then may belong to the stay before.
surgery AS (
    SELECT count(*) AS surgery_from_previous_stay
    FROM ${catalog}.gold.readmission_events s
    JOIN ${catalog}.gold.readmission_events p
      ON p.patient_id = s.patient_id AND p.stay_no = s.stay_no - 1
    JOIN ${catalog}.silver.procedure pr
      ON pr.patient_id = s.patient_id
     AND to_date(from_utc_timestamp(pr.started_at, 'America/Chicago'))
         = date_sub(to_date(from_utc_timestamp(s.admitted_at, 'America/Chicago')), 1)
    JOIN ${catalog}.gold.planned_procedure pp
      ON pp.code = pr.source_code AND pp.kind = 'heart_surgery'
    WHERE s.is_planned
      AND to_date(from_utc_timestamp(p.discharged_at, 'America/Chicago'))
          = date_sub(to_date(from_utc_timestamp(s.admitted_at, 'America/Chicago')), 1)
)
SELECT u.unknown_organization, u.unknown_provider, u.unknown_payer,
       (SELECT count(*) - count(DISTINCT organization_id) FROM ${catalog}.gold.dim_organization)
                                                                 AS duplicate_organization,
       (SELECT count(*) - count(DISTINCT provider_id) FROM ${catalog}.gold.dim_provider)
                                                                 AS duplicate_provider,
       (SELECT count(*) - count(DISTINCT payer_id) FROM ${catalog}.gold.dim_payer)
                                                                 AS duplicate_payer,
       (SELECT count(*) - count(DISTINCT date_key) FROM ${catalog}.gold.dim_date)
                                                                 AS duplicate_date,
       d.start_not_in_dim_date, d.stop_not_in_dim_date,
       abs(f.n - se.n)                                           AS fact_rows_off,
       -- Cents are rounding (round-then-add against add-then-round); a dollar is a bug.
       CASE WHEN abs(f.dollars - se.dollars) < 1 THEN 0 ELSE 1 END AS fact_dollars_off,
       abs(p.n - (SELECT count(*) FROM ${catalog}.silver.patient)) + (p.n - p.patients)
                                                                 AS patient_360_rows_off,
       abs(p.encounters - f.n)                                   AS patient_360_encounters_off,
       CASE WHEN abs(p.dollars - f.dollars) < 1 THEN 0 ELSE 1 END AS patient_360_dollars_off,
       abs(p.readmissions - ev.readmitted)                       AS patient_360_readmissions_off,
       abs(sg.n - ev.index_stays)                                AS signals_rows_off,
       sg.n - sg.keys                                            AS signals_duplicate_keys,
       st.nystatin_counted, st.statin_missed,
       su.surgery_from_previous_stay,
       -- Gold carries no governed tag: masks would rewrite the dates it needs; published as counts only (D60, D63).
       (SELECT count(*) FROM ${catalog}.information_schema.column_tags
        WHERE schema_name = 'gold')                              AS gold_tagged_columns,
       -- Every hospital encounter sits in exactly one stay (E58 broke this).
       abs(ev.encounters - (SELECT count(*) FROM ${catalog}.silver.encounter
                            WHERE readmission_role = 'index_eligible')) AS events_encounters_off
FROM unknown u
CROSS JOIN dates d
CROSS JOIN fact f
CROSS JOIN silver_encounter se
CROSS JOIN p360 p
CROSS JOIN events ev
CROSS JOIN signals sg
CROSS JOIN statin st
CROSS JOIN surgery su;
