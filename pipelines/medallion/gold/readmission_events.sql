-- One row per hospital stay, CMS-like; every exclusion its own column; Chicago calendar days (D35).

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.readmission_events (
    -- Every stay is either an index stay or excluded for a named reason.
    CONSTRAINT index_flag_known EXPECT (is_index_stay IS NOT NULL) ON VIOLATION FAIL UPDATE,
    -- A duplicated stay fails here, before the table is replaced (E59).
    CONSTRAINT one_row_per_stay EXPECT (key_copies = 1) ON VIOLATION FAIL UPDATE,
    -- Phase 8: every stay has a cost, a hospital and a payer (its first encounter's).
    CONSTRAINT stay_cost_present EXPECT (stay_claim_cost IS NOT NULL) ON VIOLATION FAIL UPDATE,
    CONSTRAINT stay_has_hospital_and_payer EXPECT (organization_id IS NOT NULL AND payer_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
    CONSTRAINT length_not_negative EXPECT (length_of_stay_days >= 0) ON VIOLATION FAIL UPDATE
)
COMMENT "One row per hospital stay (overlapping and same-day encounters merged). Every exclusion is its own column. Stay cost, length of stay, hospital and payer for every stay (phase 8)."
TBLPROPERTIES ("quality" = "gold")
AS
WITH inp AS (
    SELECT patient_id, encounter_id, started_at, stopped_at, reason_description,
           to_date(from_utc_timestamp(started_at, 'America/Chicago')) AS start_day,
           to_date(from_utc_timestamp(stopped_at, 'America/Chicago')) AS stop_day
    FROM ${catalog}.silver.encounter
    WHERE readmission_role = 'index_eligible'
),

-- A new stay starts only after every earlier encounter ended: max(), not lag().
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
    -- GROUP BY, not DISTINCT: a joined DISTINCT CTE stopped deduplicating in the pipeline (E58, E59).
    SELECT pr.encounter_id AS planned_encounter_id, count(*) AS cancer_procedures
    FROM ${catalog}.silver.procedure pr
    JOIN ${catalog}.gold.planned_procedure pp ON pp.code = pr.source_code
    WHERE pp.kind = 'cancer_treatment'
    GROUP BY pr.encounter_id
),

-- "First" by start time, then id, so engines break ties alike.
stays AS (
    SELECT patient_id, stay_no,
           min_by(encounter_id, struct(started_at, encounter_id))       AS first_encounter_id,
           -- DISTINCT: the join multiplied stays by procedure rows (E58).
           count(DISTINCT encounter_id)                                 AS encounters_in_stay,
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

-- Scheduled heart operations from the day before admission (D68); an emergency one makes the stay unplanned.
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

-- Planned follows the first reason, except cancer treatment (D64) and scheduled heart surgery (D68).
stays_p AS (
    SELECT s.*, pr.reason_description IS NOT NULL OR s.cancer_treatment
                OR ps.stay_no IS NOT NULL AS is_planned
    FROM stays s
    LEFT JOIN ${catalog}.gold.planned_reason pr ON pr.reason_description = s.admit_reason
    LEFT JOIN planned_surgery ps ON ps.patient_id = s.patient_id AND ps.stay_no = s.stay_no
),

-- Phase 8: claim cost of every stay, shared by the dashboard and the model.
stay_cost AS (
    SELECT s.patient_id, s.stay_no, sum(f.total_claim_cost) AS stay_claim_cost
    FROM stays s
    JOIN ${catalog}.gold.fact_encounter f
      ON f.patient_id = s.patient_id
     AND f.readmission_role = 'index_eligible'
     AND to_date(from_utc_timestamp(f.started_at, 'America/Chicago'))
         BETWEEN s.admit_day AND s.discharge_day
    GROUP BY s.patient_id, s.stay_no
),

-- Data ends at the last visit of any kind.
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
    SELECT s.patient_id, s.stay_no, count(*) AS hospice_visits
    FROM stays_p s
    JOIN ${catalog}.silver.encounter h
      ON h.patient_id = s.patient_id
     AND h.encounter_class = 'hospice'
     AND datediff(to_date(from_utc_timestamp(h.started_at, 'America/Chicago')),
                  s.discharge_day) BETWEEN 0 AND 1
    GROUP BY s.patient_id, s.stay_no
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
            OR s.cancer_treatment)                                 AS is_index_stay,
       -- Phase 8: the stay's hospital and payer are its first encounter's.
       fe.organization_id,
       fe.payer_id,
       datediff(s.discharge_day, s.admit_day)                      AS length_of_stay_days,
       sc.stay_claim_cost,
       -- The one-row-per-stay gate reads it (E59).
       count(*) OVER (PARTITION BY s.patient_id, s.stay_no)        AS key_copies
FROM stays_p s
CROSS JOIN data_end d
JOIN ${catalog}.silver.patient p       ON p.patient_id = s.patient_id
LEFT JOIN unplanned_return ur          ON ur.patient_id = s.patient_id AND ur.stay_no = s.stay_no
LEFT JOIN any_next nx                  ON nx.patient_id = s.patient_id AND nx.stay_no = s.stay_no
LEFT JOIN to_hospice th                ON th.patient_id = s.patient_id AND th.stay_no = s.stay_no
LEFT JOIN ${catalog}.gold.fact_encounter fe ON fe.encounter_id = s.first_encounter_id
LEFT JOIN stay_cost sc                 ON sc.patient_id = s.patient_id AND sc.stay_no = s.stay_no;
