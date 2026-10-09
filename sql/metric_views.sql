-- Phase 5 metrics layer, built after the test questions were frozen; also the metrics contestant's prompt.

CREATE SCHEMA IF NOT EXISTS healthcare_dev.metrics
COMMENT "Phase 5: every number in the readmission story, defined once, as metric views.";

CREATE OR REPLACE VIEW healthcare_dev.metrics.stays
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Every hospital stay (overlapping and same-day inpatient encounters merged into one), and why some cannot start a 30-day window. Phase 8 adds cost, length of stay, hospital and payer."
source: healthcare_dev.gold.readmission_events
joins:
  - name: org
    source: healthcare_dev.gold.dim_organization
    on: source.organization_id = org.organization_id
  - name: pay
    source: healthcare_dev.gold.dim_payer
    on: source.payer_id = pay.payer_id
dimensions:
  - name: admit_year
    expr: year(from_utc_timestamp(admitted_at, 'America/Chicago'))
  - name: is_planned
    expr: is_planned
    comment: "Planned: began for a planned reason, or included chemotherapy (D64) or a scheduled heart operation (D68). A planned return is not a readmission."
  - name: admit_month
    expr: trunc(to_date(from_utc_timestamp(admitted_at, 'America/Chicago')), 'MM')
    comment: "First day of the month the stay began, Chicago time."
  - name: admit_quarter
    expr: trunc(to_date(from_utc_timestamp(admitted_at, 'America/Chicago')), 'QUARTER')
    comment: "First day of the quarter the stay began, Chicago time."
  - name: hospital
    expr: concat_ws(', ', org.name, org.city)
    comment: "The hospital of the first encounter in the stay, as name and city."
  - name: payer
    expr: pay.name
    comment: "The payer of the first encounter in the stay."
measures:
  - name: stays
    expr: count(*)
  - name: encounters_merged
    expr: sum(encounters_in_stay) - count(*)
    comment: "Encounters that were part of a longer stay."
  - name: excluded_died
    expr: count_if(excl_died_during_stay)
  - name: excluded_short_followup
    expr: count_if(excl_short_followup)
    comment: "Fewer than 30 days of data after discharge."
  - name: excluded_hospice
    expr: count_if(excl_discharged_to_hospice)
  - name: excluded_cancer_treatment
    expr: count_if(excl_cancer_treatment)
    comment: "Stays that included chemotherapy: planned, and cannot start a window (D64)."
  - name: index_stays
    expr: count_if(is_index_stay)
    comment: "Stays that can start a 30-day window."
  - name: stay_cost
    expr: sum(stay_claim_cost)
    comment: "Claim cost of the stays, in dollars."
  - name: cost_per_stay
    expr: try_divide(sum(stay_claim_cost), count(*))
    comment: "Claim cost per stay, in dollars. Every stay, not only index stays."
  - name: avg_length_of_stay_days
    expr: avg(length_of_stay_days)
    comment: "Days from admit day to discharge day, Chicago time. Every stay."
$$;

CREATE OR REPLACE VIEW healthcare_dev.metrics.readmission
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "One row per index stay, with its 30-day readmission and every signal the readmission story tests. post_followup_7d is known only after discharge: it explains readmissions and cannot predict them."
source: healthcare_dev.gold.readmission_signals
dimensions:
  - name: admit_year
    expr: admit_year
  - name: admit_period
    expr: CASE WHEN admit_year < 1990 THEN '1915-1989' WHEN admit_year < 2000 THEN '1990-1999' WHEN admit_year < 2010 THEN '2000-2009' WHEN admit_year < 2020 THEN '2010-2019' ELSE '2020-2026' END
    comment: "Year admitted, in periods wide enough that no period has 1-10 readmissions (D70)."
  - name: age_band
    expr: age_band
    comment: "Age on the admit day: 0-17, 18-44, 45-64, 65-79 or 80+."
  - name: gender
    expr: gender
    comment: "M or F."
  - name: has_diabetes
    expr: has_diabetes
    comment: "Type 2 diabetes open on the admit day."
  - name: has_hypertension
    expr: has_hypertension
    comment: "Essential hypertension open on the admit day."
  - name: has_cardiovascular_disease
    expr: has_cardiovascular_disease
    comment: "Heart disease or stroke open on the admit day."
  - name: above_median_conditions
    expr: above_median_conditions
    comment: "More conditions open on the admit day than the median index stay."
  - name: admit_reason_group
    expr: admit_reason_group
    comment: "Why the stay began: the five commonest reasons by name, the rest as other."
  - name: is_planned
    expr: is_planned
  - name: above_median_length_of_stay
    expr: above_median_length_of_stay
    comment: "Longer than the median index stay, in days."
  - name: prior_stays_12m_band
    expr: CASE WHEN prior_stays_12m >= 2 THEN '2+' ELSE cast(prior_stays_12m AS STRING) END
    comment: "Hospital stays in the 365 days before admission: 0, 1 or 2+."
  - name: prior_emergency_12m_band
    expr: CASE WHEN prior_emergency_12m >= 1 THEN '1+' ELSE '0' END
    comment: "Emergency visits in the 365 days before admission: 0 or 1+."
  - name: post_followup_7d
    expr: post_followup_7d
    comment: "AFTER DISCHARGE. A clinic or wellness visit 1-7 days after discharge, before any further stay."
measures:
  - name: index_stays
    expr: count(*)
  - name: readmitted
    expr: count_if(outcome_readmitted_30d)
    comment: "Followed by an unplanned stay 1-30 days after discharge."
  - name: readmission_rate_pct
    expr: 100 * try_divide(count_if(outcome_readmitted_30d), count(*))
    comment: "Readmitted as a percentage of index stays. Not rounded."
  - name: patients
    expr: count(DISTINCT patient_id)
  - name: readmitted_patients
    expr: count(DISTINCT CASE WHEN outcome_readmitted_30d THEN patient_id END)
  - name: index_stay_cost
    expr: sum(stay_claim_cost)
    comment: "Claim cost of the index stays, in dollars."
  - name: return_stay_cost
    expr: sum(outcome_return_stay_cost)
    comment: "Claim cost of the stays that made index stays into readmissions, in dollars."
  - name: avg_length_of_stay_days
    expr: avg(length_of_stay_days)
$$;

CREATE OR REPLACE VIEW healthcare_dev.metrics.operations
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Phase 8. Every visit of any kind, for the operations dashboard."
source: healthcare_dev.gold.fact_encounter
joins:
  - name: org
    source: healthcare_dev.gold.dim_organization
    on: source.organization_id = org.organization_id
  - name: pay
    source: healthcare_dev.gold.dim_payer
    on: source.payer_id = pay.payer_id
dimensions:
  - name: visit_month
    expr: trunc(to_date(from_utc_timestamp(source.started_at, 'America/Chicago')), 'MM')
    comment: "First day of the month the visit started, Chicago time."
  - name: visit_type
    expr: source.encounter_class
    comment: "The visit class as recorded: ambulatory, wellness, outpatient, emergency, inpatient, urgentcare and others."
  - name: hospital
    expr: concat_ws(', ', org.name, org.city)
    comment: "The organization that held the visit, as name and city."
  - name: payer
    expr: pay.name
measures:
  - name: visits
    expr: count(*)
  - name: patients
    expr: count(DISTINCT source.patient_id)
$$;

CREATE OR REPLACE VIEW healthcare_dev.metrics.care_gaps
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Phase 8. Three HEDIS-style care-gap measures, simplified, for the one measure year in gold."
source: healthcare_dev.gold.care_gap
dimensions:
  - name: measure
    expr: measure
    comment: "diabetes_hba1c, bp_control or statin_therapy."
  - name: measure_year
    expr: measure_year
measures:
  - name: eligible
    expr: count_if(NOT (excl_age OR excl_died OR excl_hospice))
    comment: "In the measure and not excused by age, death or hospice."
  - name: closed
    expr: count_if(NOT (excl_age OR excl_died OR excl_hospice) AND numerator_met)
    comment: "Eligible and got the care the measure asks for."
  - name: closure_rate_pct
    expr: 100 * try_divide(count_if(NOT (excl_age OR excl_died OR excl_hospice) AND numerator_met), count_if(NOT (excl_age OR excl_died OR excl_hospice)))
    comment: "Closed as a percentage of eligible. Not rounded."
$$;