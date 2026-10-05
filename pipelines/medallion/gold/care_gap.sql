-- Three HEDIS-style measures: who should get something (denominator), who
-- got it (numerator), who is excused (one column per exclusion). Measured
-- over the last complete calendar year (probe P5: 2025).

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.care_gap (
    -- A duplicated patient-measure fails here, before the table is replaced (E59).
    CONSTRAINT one_row_per_patient_measure EXPECT (key_copies = 1) ON VIOLATION FAIL UPDATE
)
COMMENT "One row per patient per measure per year. gap = should have had it, was not excused, did not get it."
TBLPROPERTIES ("quality" = "gold")
AS
WITH period AS (
    SELECT year(max(started_at)) - 1                     AS measure_year,
           make_date(year(max(started_at)) - 1, 1, 1)    AS period_start,
           make_date(year(max(started_at)) - 1, 12, 31)  AS period_end
    FROM ${catalog}.silver.encounter
),

-- Had the condition at some point during the year, and was alive when it
-- began. Synthea rarely closes a diagnosis, so without the second rule
-- everyone who ever died with one would sit in the population as "died".
denominator AS (
    -- GROUP BY with a count, not SELECT DISTINCT: inside the pipeline a DISTINCT
    -- CTE that is joined afterwards stopped removing duplicates (E58, E59).
    SELECT c.patient_id, mc.measure, count(*) AS condition_rows
    FROM ${catalog}.silver.condition c
    JOIN ${catalog}.gold.measure_code mc
      ON mc.role = 'denominator' AND mc.source = 'condition' AND mc.code = c.source_code
    JOIN ${catalog}.silver.patient p ON p.patient_id = c.patient_id
    CROSS JOIN period pr
    WHERE c.onset_date <= pr.period_end
      AND (c.resolved_date IS NULL OR c.resolved_date >= pr.period_start)
      AND (p.death_date IS NULL OR p.death_date >= pr.period_start)
    GROUP BY c.patient_id, mc.measure
),

hba1c_done AS (
    SELECT o.patient_id, count(*) AS tests
    FROM ${catalog}.silver.observation o
    JOIN ${catalog}.gold.measure_code mc
      ON mc.measure = 'diabetes_hba1c' AND mc.role = 'numerator' AND mc.code = o.source_code
    CROSS JOIN period pr
    WHERE to_date(o.observed_at) BETWEEN pr.period_start AND pr.period_end
    GROUP BY o.patient_id
),

-- Blood pressure is two observations taken together. Pair them by moment,
-- keep the last pair of the year, and judge that one.
bp_pairs AS (
    SELECT o.patient_id, o.observed_at,
           max(CASE WHEN o.source_code = '8480-6' THEN o.value_number END) AS systolic,
           max(CASE WHEN o.source_code = '8462-4' THEN o.value_number END) AS diastolic
    FROM ${catalog}.silver.observation o
    CROSS JOIN period pr
    WHERE o.source_code IN ('8480-6', '8462-4')
      AND to_date(o.observed_at) BETWEEN pr.period_start AND pr.period_end
    GROUP BY o.patient_id, o.observed_at
    HAVING systolic IS NOT NULL AND diastolic IS NOT NULL
),
bp_controlled AS (
    SELECT patient_id
    FROM (SELECT patient_id, max_by(struct(systolic, diastolic), observed_at) AS last_bp
          FROM bp_pairs GROUP BY patient_id)
    WHERE last_bp.systolic < 140 AND last_bp.diastolic < 90
),

-- Whole-word match on the generic name: '\\b' is a word boundary.
statin_taken AS (
    SELECT m.patient_id, count(*) AS prescriptions
    FROM ${catalog}.silver.medication m
    JOIN ${catalog}.gold.measure_code mc
      ON mc.measure = 'statin_therapy' AND mc.role = 'numerator'
     AND lower(m.source_description) RLIKE concat('\\b', mc.code, '\\b')
    CROSS JOIN period pr
    WHERE to_date(m.started_at) <= pr.period_end
      AND (m.stopped_at IS NULL OR to_date(m.stopped_at) >= pr.period_start)
    GROUP BY m.patient_id
),

in_hospice AS (
    SELECT e.patient_id, count(*) AS hospice_visits
    FROM ${catalog}.silver.encounter e CROSS JOIN period pr
    WHERE e.encounter_class = 'hospice'
      AND to_date(e.started_at) BETWEEN pr.period_start AND pr.period_end
    GROUP BY e.patient_id
),

flagged AS (
    SELECT d.patient_id, d.measure, pr.measure_year,
           floor(months_between(pr.period_end, p.birth_date) / 12) AS age_at_year_end,
           coalesce(p.death_date <= pr.period_end, false)          AS excl_died,
           h.patient_id IS NOT NULL                                AS excl_hospice,
           CASE d.measure
               WHEN 'diabetes_hba1c' THEN hb.patient_id IS NOT NULL
               WHEN 'bp_control'     THEN bp.patient_id IS NOT NULL
               WHEN 'statin_therapy' THEN st.patient_id IS NOT NULL
           END                                                     AS numerator_met
    FROM denominator d
    CROSS JOIN period pr
    JOIN ${catalog}.silver.patient p ON p.patient_id = d.patient_id
    LEFT JOIN in_hospice h     ON h.patient_id  = d.patient_id
    LEFT JOIN hba1c_done hb    ON hb.patient_id = d.patient_id
    LEFT JOIN bp_controlled bp ON bp.patient_id = d.patient_id
    LEFT JOIN statin_taken st  ON st.patient_id = d.patient_id
),

-- HEDIS age bands, simplified: diabetes 18-75, blood pressure 18-85,
-- statins 21-75.
aged AS (
    SELECT *,
           NOT CASE measure
               WHEN 'diabetes_hba1c' THEN age_at_year_end BETWEEN 18 AND 75
               WHEN 'bp_control'     THEN age_at_year_end BETWEEN 18 AND 85
               WHEN 'statin_therapy' THEN age_at_year_end BETWEEN 21 AND 75
           END AS excl_age
    FROM flagged
)

SELECT patient_id, measure, measure_year, age_at_year_end,
       excl_age, excl_died, excl_hospice, numerator_met,
       NOT (excl_age OR excl_died OR excl_hospice) AND NOT numerator_met AS gap,
       -- The one-row-per-patient-measure gate reads it (E59).
       count(*) OVER (PARTITION BY patient_id, measure, measure_year) AS key_copies
FROM aged;
