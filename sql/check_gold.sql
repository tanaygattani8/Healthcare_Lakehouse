-- The gold report: numbers to read; invariants are pipeline gates since D73.

-- Reference tables and the visit fact (their checks are gates in gold_checks.sql).
SELECT min(calendar_date), max(calendar_date), count(*) AS days
FROM healthcare_dev.gold.dim_date;

-- Step 3, check B: the gate's rules on silver; must equal 1,292 / 24 / 3 / 1,265 / 202 bar quarantine.
WITH inp AS (
    SELECT patient_id, started_at AS admitted, stopped_at AS discharged,
           lead(started_at) OVER (PARTITION BY patient_id ORDER BY started_at) AS next_admitted
    FROM healthcare_dev.silver.encounter WHERE encounter_class = 'inpatient'
),
b AS (SELECT max(discharged) AS data_end FROM inp),
f AS (
    SELECT i.*,
           coalesce(p.death_date <= to_date(i.discharged), false) AS died,
           datediff(b.data_end, i.discharged) < 30                AS short,
           i.next_admitted IS NOT NULL
             AND datediff(i.next_admitted, i.discharged) BETWEEN 1 AND 30 AS readmitted
    FROM inp i CROSS JOIN b
    JOIN healthcare_dev.silver.patient p USING (patient_id)
)
SELECT count(*) AS inpatient_encounters,
       count_if(died) AS excluded_death,
       count_if(short AND NOT died) AS excluded_short_followup,
       count_if(NOT died AND NOT short) AS index_admissions,
       count_if(NOT died AND NOT short AND readmitted) AS readmissions
FROM f;

SELECT count(*) AS inpatient_encounters_quarantined
FROM healthcare_dev.ops.quarantine_encounter WHERE encounter_class = 'inpatient';

-- Step 3, check C: expect 14,313 stays, 1,382 merged, 10,724 index stays, 140 readmitted.
SELECT count(*)                                         AS stays,
       sum(encounters_in_stay) - count(*)               AS encounters_merged_away,
       count_if(excl_died_during_stay)                  AS excl_died,
       count_if(excl_short_followup)                    AS excl_short_followup,
       count_if(excl_discharged_to_hospice)             AS excl_hospice,
       count_if(excl_cancer_treatment)                  AS excl_cancer_treatment,
       count_if(is_index_stay)                          AS index_stays,
       count_if(is_index_stay AND readmitted_30d)       AS readmitted,
       round(100 * count_if(is_index_stay AND readmitted_30d)
             / count_if(is_index_stay), 2)              AS readmission_rate_pct,
       count_if(is_index_stay AND days_to_next_stay BETWEEN 1 AND 30
                AND NOT readmitted_30d)                 AS returns_not_counted_planned
FROM healthcare_dev.gold.readmission_events;

-- Step 3, check D: the patient with the most merged encounters, to compare by hand.
SELECT stay_no, encounters_in_stay, admitted_at, discharged_at,
       days_to_next_stay, readmitted_30d
FROM healthcare_dev.gold.readmission_events
WHERE patient_id = (SELECT max_by(patient_id, encounters_in_stay)
                    FROM healthcare_dev.gold.readmission_events)
ORDER BY stay_no;

-- Step 4: one line per measure; every column is a count except the rate.
SELECT measure, measure_year,
       count(*)                                              AS in_denominator,
       count_if(excl_age)                                    AS excl_age,
       count_if(excl_died)                                   AS excl_died,
       count_if(excl_hospice)                                AS excl_hospice,
       count_if(NOT (excl_age OR excl_died OR excl_hospice)) AS eligible,
       count_if(numerator_met AND NOT (excl_age OR excl_died OR excl_hospice)) AS met,
       count_if(gap)                                         AS gaps,
       round(100 * count_if(numerator_met AND NOT (excl_age OR excl_died OR excl_hospice))
             / count_if(NOT (excl_age OR excl_died OR excl_hospice)), 1) AS met_pct
FROM healthcare_dev.gold.care_gap
GROUP BY measure, measure_year ORDER BY measure;

-- Medication rows the statin rule matches.
SELECT count_if(hit.code IS NOT NULL) AS statin_rows_matched
FROM healthcare_dev.silver.medication m
LEFT JOIN healthcare_dev.gold.measure_code hit
  ON hit.measure = 'statin_therapy' AND hit.role = 'numerator'
 AND lower(m.source_description) RLIKE concat('\\b', hit.code, '\\b')
WHERE lower(m.source_description) LIKE '%statin%';

-- Step 5: patient_360 totals and gold tags are gates now (gold_checks.sql).

-- Phase 5: readmission_signals, expect rows = 10724, readmitted = 140 (D68).
SELECT count(*) AS rows, count_if(outcome_readmitted_30d) AS readmitted
FROM healthcare_dev.gold.readmission_signals;

-- What the story splits on. Six rows: five names and "other".
SELECT admit_reason_group, count(*) AS index_stays,
       count_if(outcome_readmitted_30d) AS readmitted
FROM healthcare_dev.gold.readmission_signals
GROUP BY ALL ORDER BY index_stays DESC;

-- The two medians, and how many stays sit on each side of them.
SELECT median(conditions_at_admit) AS conditions_median,
       count_if(above_median_conditions) AS above_conditions,
       median(length_of_stay_days) AS length_of_stay_median,
       count_if(above_median_length_of_stay) AS above_length_of_stay,
       count_if(post_followup_7d) AS followed_up_7d,
       count_if(prior_stays_12m >= 1) AS had_prior_stay
FROM healthcare_dev.gold.readmission_signals;

-- D68's day-before window is a gate now: gold_checks.surgery_from_previous_stay.

-- Phase 6 split: expect all 10724 / 140, no_bypass 9891 / 61, production 2451 / 34; write 1-10 as "1-10".
WITH s AS (
    SELECT *,
           CASE WHEN admit_day >= DATE'2020-01-01' THEN 'production'
                WHEN discharge_day <= DATE'2019-12-01' THEN 'training'
                ELSE 'gap' END AS part
    FROM healthcare_dev.gold.readmission_signals
)
SELECT part,
       count(*)                                                    AS all_stays,
       count_if(outcome_readmitted_30d)                            AS all_readmitted,
       count_if(NOT had_bypass_surgery)                            AS no_bypass_stays,
       count_if(NOT had_bypass_surgery AND outcome_readmitted_30d) AS no_bypass_readmitted
FROM s
GROUP BY ROLLUP(part)
ORDER BY part;

-- First stays (no earlier discharge): expect 4956.
SELECT count_if(days_since_last_discharge IS NULL) AS first_stays
FROM healthcare_dev.gold.readmission_signals;
