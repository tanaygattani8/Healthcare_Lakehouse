-- Check C ladder: switch each change on one at a time, from the gate (B) to
-- the real table. v2 = merge stays; v3 = + local days; v4 = + data ends at
-- the last visit of any kind; v5 = + planned returns do not count; v6 = +
-- a cancer treatment stay is planned; v7 = + it cannot start a window
-- either (D64) (= table).
WITH variant AS (
    SELECT * FROM VALUES (2, false, false, false, false, false),
                         (3, true, false, false, false, false),
                         (4, true, true, false, false, false),
                         (5, true, true, true, false, false),
                         (6, true, true, true, true, false),
                         (7, true, true, true, true, true)
    AS t(v, local_days, end_any, use_planned, cancer_planned, cancer_excluded)
),
planned_encounter AS (
    SELECT DISTINCT pr.encounter_id AS planned_encounter_id
    FROM healthcare_dev.silver.procedure pr
    JOIN healthcare_dev.gold.planned_procedure pp ON pp.code = pr.source_code
),
inp AS (
    SELECT v.*, e.patient_id, e.encounter_id, e.started_at, e.stopped_at, e.reason_description,
           pe.planned_encounter_id IS NOT NULL AS planned_encounter,
           CASE WHEN v.local_days THEN to_date(from_utc_timestamp(e.started_at, 'America/Chicago'))
                ELSE to_date(e.started_at) END AS start_day,
           CASE WHEN v.local_days THEN to_date(from_utc_timestamp(e.stopped_at, 'America/Chicago'))
                ELSE to_date(e.stopped_at) END AS stop_day
    FROM healthcare_dev.silver.encounter e CROSS JOIN variant v
    LEFT JOIN planned_encounter pe ON pe.planned_encounter_id = e.encounter_id
    WHERE e.readmission_role = 'index_eligible'
),
marked AS (
    SELECT *, CASE WHEN max(stop_day) OVER w IS NULL OR start_day > max(stop_day) OVER w
                   THEN 1 ELSE 0 END AS new_stay
    FROM inp
    WINDOW w AS (PARTITION BY v, patient_id ORDER BY started_at, encounter_id
                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
),
numbered AS (
    SELECT *, sum(new_stay) OVER (PARTITION BY v, patient_id ORDER BY started_at, encounter_id
                                  ROWS UNBOUNDED PRECEDING) AS stay_no
    FROM marked
),
stays AS (
    SELECT v, local_days, end_any, use_planned, cancer_planned, cancer_excluded,
           patient_id, stay_no,
           min(start_day) AS admit_day, max(stop_day) AS discharge_day,
           min_by(reason_description, struct(started_at, encounter_id)) AS admit_reason,
           max(planned_encounter) AS cancer_treatment
    FROM numbered GROUP BY ALL
),
stays_p AS (
    SELECT s.*, (use_planned AND pr.reason_description IS NOT NULL)
              OR (cancer_planned AND cancer_treatment) AS is_planned
    FROM stays s LEFT JOIN healthcare_dev.gold.planned_reason pr
      ON pr.reason_description = s.admit_reason
),
ends AS (
    SELECT to_date(max(stopped_at) FILTER (WHERE readmission_role = 'index_eligible')) AS utc_inp_end,
           to_date(from_utc_timestamp(max(stopped_at) FILTER (WHERE readmission_role = 'index_eligible'),
                                      'America/Chicago'))                             AS local_inp_end,
           to_date(from_utc_timestamp(max(started_at), 'America/Chicago'))             AS local_any_end
    FROM healthcare_dev.silver.encounter
),
ret AS (
    SELECT a.v, a.patient_id, a.stay_no
    FROM stays_p a JOIN stays_p b
      ON b.v = a.v AND b.patient_id = a.patient_id AND b.stay_no > a.stay_no
     AND NOT b.is_planned AND datediff(b.admit_day, a.discharge_day) BETWEEN 1 AND 30
    GROUP BY ALL
),
f AS (
    SELECT s.v,
           coalesce(p.death_date <= s.discharge_day, false) AS died,
           datediff(CASE WHEN s.end_any THEN e.local_any_end
                         WHEN s.local_days THEN e.local_inp_end
                         ELSE e.utc_inp_end END, s.discharge_day) < 30 AS short,
           s.cancer_excluded AND s.cancer_treatment AS cancer,
           r.v IS NOT NULL AS readmitted
    FROM stays_p s CROSS JOIN ends e
    JOIN healthcare_dev.silver.patient p ON p.patient_id = s.patient_id
    LEFT JOIN ret r ON r.v = s.v AND r.patient_id = s.patient_id AND r.stay_no = s.stay_no
)
SELECT v, count(*) AS stays, count_if(died) AS died, count_if(short AND NOT died) AS short,
       count_if(cancer AND NOT died AND NOT short) AS cancer,
       count_if(NOT died AND NOT short AND NOT cancer) AS index_stays,
       count_if(NOT died AND NOT short AND NOT cancer AND readmitted) AS readmitted,
       round(100 * count_if(NOT died AND NOT short AND NOT cancer AND readmitted)
             / count_if(NOT died AND NOT short AND NOT cancer), 2) AS rate_pct
FROM f GROUP BY v ORDER BY v;
