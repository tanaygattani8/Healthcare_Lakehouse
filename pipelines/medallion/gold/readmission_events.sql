-- One row per hospital STAY, CMS-like, simplified. Every exclusion is its own
-- column, never a hidden WHERE, so a reader can see why a stay was dropped.
--
-- Days are calendar days in America/Chicago, where Synthea generated the
-- data (D35); silver stores UTC, and an evening discharge in Chicago is the
-- next day in UTC.

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.readmission_events
COMMENT "One row per hospital stay (overlapping and same-day encounters merged). Every exclusion is its own column."
TBLPROPERTIES ("quality" = "gold")
AS
WITH inp AS (
    SELECT patient_id, encounter_id, started_at, stopped_at, reason_description,
           to_date(from_utc_timestamp(started_at, 'America/Chicago')) AS start_day,
           to_date(from_utc_timestamp(stopped_at, 'America/Chicago')) AS stop_day
    FROM ${catalog}.silver.encounter
    WHERE readmission_role = 'index_eligible'
),

-- A new stay begins only if this encounter starts on a later day than every
-- earlier one ended. max() over all earlier rows, not lag(): a long stay can
-- swallow several short ones, and lag() only sees the one just before.
marked AS (
    SELECT *,
           CASE WHEN max(stop_day) OVER w IS NULL OR start_day > max(stop_day) OVER w
                THEN 1 ELSE 0 END AS starts_new_stay
    FROM inp
    WINDOW w AS (PARTITION BY patient_id ORDER BY started_at, encounter_id
                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
),

numbered AS (
    SELECT *,
           sum(starts_new_stay) OVER (
               PARTITION BY patient_id ORDER BY started_at, encounter_id
               ROWS UNBOUNDED PRECEDING) AS stay_no
    FROM marked
),

-- Encounters with a procedure that is always planned: cancer treatment (D64).
planned_encounter AS (
    SELECT DISTINCT pr.encounter_id AS planned_encounter_id
    FROM ${catalog}.silver.procedure pr
    JOIN ${catalog}.gold.planned_procedure pp ON pp.code = pr.source_code
    WHERE pp.kind = 'cancer_treatment'
),

-- "First" is by start time, then id: two encounters can start at the same
-- moment, and a tie broken at random would differ between engines.
stays AS (
    SELECT patient_id, stay_no,
           min_by(encounter_id, struct(started_at, encounter_id))       AS first_encounter_id,
           count(*)                                                     AS encounters_in_stay,
           min(started_at)                                              AS admitted_at,
           max(stopped_at)                                              AS discharged_at,
           min(start_day)                                               AS admit_day,
           max(stop_day)                                                AS discharge_day,
           min_by(reason_description, struct(started_at, encounter_id)) AS admit_reason,
           max(planned_encounter_id IS NOT NULL)                        AS cancer_treatment
    FROM numbered
    LEFT JOIN planned_encounter ON planned_encounter_id = encounter_id
    GROUP BY patient_id, stay_no
),

-- Stays with a scheduled heart operation (D68), by day, not by encounter:
-- Synthea records a CABG on the ambulatory visit just before the inpatient
-- stay, so the window starts the day before admission. An emergency
-- operation in the window makes the stay unplanned.
-- ponytail: a surgery on the previous stay's discharge day would also land
-- in the window; no stay here starts the day after a heart operation ended one.
planned_surgery AS (
    SELECT s.patient_id, s.stay_no
    FROM stays s
    JOIN ${catalog}.silver.procedure pr
      ON pr.patient_id = s.patient_id
     AND to_date(from_utc_timestamp(pr.started_at, 'America/Chicago'))
         BETWEEN date_sub(s.admit_day, 1) AND s.discharge_day
    JOIN ${catalog}.gold.planned_procedure pp
      ON pp.code = pr.source_code AND pp.kind IN ('heart_surgery', 'emergency_heart_surgery')
    GROUP BY s.patient_id, s.stay_no
    HAVING NOT max(pp.kind = 'emergency_heart_surgery')
),

-- Planned follows the reason the stay BEGAN with: an emergency admission
-- that later merges with a planned encounter is still an emergency. The
-- exceptions are cancer treatment (D64) and scheduled heart surgery (D68),
-- which are planned wherever they fall.
stays_p AS (
    SELECT s.*, pr.reason_description IS NOT NULL OR s.cancer_treatment
                OR ps.stay_no IS NOT NULL AS is_planned
    FROM stays s
    LEFT JOIN ${catalog}.gold.planned_reason pr ON pr.reason_description = s.admit_reason
    LEFT JOIN planned_surgery ps ON ps.patient_id = s.patient_id AND ps.stay_no = s.stay_no
),

-- The end of the data: the last visit of any kind, not just the last
-- hospital stay (the gate used the latter, which ends the data early).
data_end AS (
    SELECT to_date(from_utc_timestamp(max(started_at), 'America/Chicago')) AS last_day
    FROM ${catalog}.silver.encounter
),

-- First unplanned stay 1-30 days after each discharge.
unplanned_return AS (
    SELECT a.patient_id, a.stay_no,
           min(datediff(b.admit_day, a.discharge_day)) AS days_to_unplanned_return
    FROM stays_p a
    JOIN stays_p b
      ON b.patient_id = a.patient_id
     AND b.stay_no > a.stay_no
     AND NOT b.is_planned
     AND datediff(b.admit_day, a.discharge_day) BETWEEN 1 AND 30
    GROUP BY a.patient_id, a.stay_no
),

any_next AS (
    SELECT patient_id, stay_no,
           datediff(lead(admit_day) OVER (PARTITION BY patient_id ORDER BY stay_no),
                    discharge_day) AS days_to_next_stay
    FROM stays_p
),

to_hospice AS (
    SELECT DISTINCT s.patient_id, s.stay_no
    FROM stays_p s
    JOIN ${catalog}.silver.encounter h
      ON h.patient_id = s.patient_id
     AND h.encounter_class = 'hospice'
     AND datediff(to_date(from_utc_timestamp(h.started_at, 'America/Chicago')),
                  s.discharge_day) BETWEEN 0 AND 1
)

SELECT s.patient_id,
       s.stay_no,
       s.first_encounter_id,
       s.encounters_in_stay,
       s.admitted_at,
       s.discharged_at,
       s.admit_reason,
       s.is_planned,
       -- exclusions: each its own column
       coalesce(p.death_date <= s.discharge_day, false)            AS excl_died_during_stay,
       datediff(d.last_day, s.discharge_day) < 30                  AS excl_short_followup,
       th.stay_no IS NOT NULL                                      AS excl_discharged_to_hospice,
       s.cancer_treatment                                          AS excl_cancer_treatment,
       -- outcome
       nx.days_to_next_stay,
       ur.days_to_unplanned_return,
       ur.days_to_unplanned_return IS NOT NULL                     AS readmitted_30d,
       NOT (coalesce(p.death_date <= s.discharge_day, false)
            OR datediff(d.last_day, s.discharge_day) < 30
            OR th.stay_no IS NOT NULL
            OR s.cancer_treatment)                                 AS is_index_stay
FROM stays_p s
CROSS JOIN data_end d
JOIN ${catalog}.silver.patient p       ON p.patient_id = s.patient_id
LEFT JOIN unplanned_return ur          ON ur.patient_id = s.patient_id AND ur.stay_no = s.stay_no
LEFT JOIN any_next nx                  ON nx.patient_id = s.patient_id AND nx.stay_no = s.stay_no
LEFT JOIN to_hospice th                ON th.patient_id = s.patient_id AND th.stay_no = s.stay_no;
