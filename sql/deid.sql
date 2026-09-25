-- Phase 3b step 6 — the de-identified copy, in the deid schema.
--
-- gold keeps reading the real silver. If gold used this copy, every mistake in
-- it would quietly become a wrong analytics number.
--
-- What is kept, changed, or dropped (decision.md D55):
--   names, SSN, licence, passport, address, city, county, FIPS, coordinates,
--   birthplace, file names ............ dropped from tables; [NAME] in notes
--   birth and death date .............. 5-year band; blank if fewer than 5
--                                       people share band + gender + death
--                                       band (step 7, k >= 5); blank for 90+
--   ZIP ............................... dropped. Safe Harbor allows 3 digits,
--                                       but with them 471 of 1,148 people were
--                                       alone in their group (decision.md D56)
--   encounter and note dates .......... moved by one random number of days per
--                                       patient, so every gap between visits
--                                       is unchanged. NOT Safe Harbor, which
--                                       allows the year only — the standard
--                                       research compromise, said out loud.
--   patient_id ........................ replaced by a new random deid_id

-- The secrets. One row per patient: a new id and a random shift, drawn ONCE
-- and kept. The plan computed the shift from hash(patient_id) and kept
-- patient_id in the copy — anyone with the copy and this repo could undo it.
-- Lives in ops, never in deid, and never leaves the lakehouse.
CREATE TABLE IF NOT EXISTS healthcare_dev.ops.deid_key (
    patient_id  STRING,
    deid_id     STRING,
    offset_days INT
)
COMMENT "Re-identification key for the deid schema: new id and date shift per patient. Anyone holding this and the deid tables can reverse them.";

-- New patients get a key; existing ones keep theirs, so reruns are stable.
INSERT INTO healthcare_dev.ops.deid_key
SELECT p.patient_id, uuid(), cast(floor(rand() * 364) + 1 AS INT)
FROM healthcare_dev.silver.patient p
LEFT ANTI JOIN healthcare_dev.ops.deid_key k USING (patient_id);

-- Replaces private text inside a note, working from the end so earlier
-- positions stay valid. Overlapping spans keep the first-starting, longest.
CREATE OR REPLACE FUNCTION healthcare_dev.ops.deid_text(
    note STRING, spans ARRAY<STRUCT<s: INT, e: INT, k: STRING, t: STRING>>, shift INT)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'Redact one note: [NAME] for names, dates moved by shift days, 90+ for ages over 89.'
AS $$
from datetime import date, timedelta

def replacement(kind, text):
    if kind == "date":
        try:
            return (date.fromisoformat(text) + timedelta(days=shift)).isoformat()
        except ValueError:
            return "[DATE]"
    if kind == "age":
        return "90+"
    return "[NAME]"

kept, end = [], -1
for span in sorted(spans or [], key=lambda x: (x["s"], -x["e"])):
    if span["s"] >= end:
        kept.append(span)
        end = span["e"]
for span in reversed(kept):
    # The positions were measured on the laptop's copy of the note. If this
    # copy differs by one character, every replacement lands in the wrong
    # place and garbles the note silently — so stop instead.
    if note[span["s"]:span["e"]] != span["t"]:
        raise ValueError(f"answer-sheet position {span['s']} does not match the note")
    note = note[:span["s"]] + replacement(span["k"], span["t"]) + note[span["e"]:]
return note
$$;

CREATE OR REPLACE TABLE healthcare_dev.deid.patient
COMMENT "De-identified patients. 5-year birth and death bands, blank where fewer than 5 people share band + gender + death band, and for 90+. No ZIP, names or identifiers. Join on deid_id."
AS
WITH aged AS (
    SELECT p.*, k.deid_id,
           floor(months_between(coalesce(p.death_date, current_date()), p.birth_date) / 12) AS age
    FROM healthcare_dev.silver.patient p
    JOIN healthcare_dev.ops.deid_key k USING (patient_id)
),
banded AS (
    SELECT *,
           CASE WHEN age <= 89 THEN cast(floor(year(birth_date) / 5) * 5 AS INT) END AS birth_band,
           CASE WHEN age <= 89 THEN cast(floor(year(death_date) / 5) * 5 AS INT) END AS death_band
    FROM aged
),
-- k = how many people share this combination. Below 5, the bands are blanked
-- (step 7, decision.md D56). The blanked people then share one large group.
counted AS (
    SELECT *, count(*) OVER (PARTITION BY birth_band, GENDER, death_band) AS k
    FROM banded
)
SELECT deid_id,
       CASE WHEN k >= 5 THEN birth_band END AS birth_year_from,
       CASE WHEN k >= 5 THEN death_band END AS death_year_from,
       CASE WHEN age > 89 THEN '90+' END    AS age_band,
       k < 5 AS years_suppressed,
       is_deceased, GENDER AS gender, RACE AS race, ETHNICITY AS ethnicity,
       MARITAL AS marital, STATE AS state,
       healthcare_expenses, healthcare_coverage, income
FROM counted;

CREATE OR REPLACE TABLE healthcare_dev.deid.encounter
COMMENT "De-identified encounters. Timestamps moved by the patient's own shift, so gaps between visits are exact. Organisation and provider dropped."
AS
SELECT k.deid_id,
       e.started_at + make_dt_interval(k.offset_days) AS started_at,
       e.stopped_at + make_dt_interval(k.offset_days) AS stopped_at,
       e.encounter_class, e.canonical_class, e.readmission_role,
       e.reason_code_key, e.reason_description,
       e.base_cost, e.total_claim_cost, e.payer_coverage
FROM healthcare_dev.silver.encounter e
JOIN healthcare_dev.ops.deid_key k USING (patient_id);

CREATE OR REPLACE TABLE healthcare_dev.deid.note
COMMENT "De-identified notes. Private text found by the patient's own details (Program 0, 1.000 on the test set) replaced: [NAME], dates moved by the patient's shift, 90+."
AS
WITH spans AS (
    SELECT patient_id,
           collect_list(named_struct('s', char_start, 'e', char_end,
                                     'k', phi_category, 't', surface_text)) AS spans
    FROM healthcare_dev.silver.phi_span
    GROUP BY patient_id
)
SELECT k.deid_id,
       healthcare_dev.ops.deid_text(n.note_text, s.spans, k.offset_days) AS note_text
FROM healthcare_dev.bronze.br_notes n
JOIN healthcare_dev.ops.deid_key k USING (patient_id)
LEFT JOIN spans s USING (patient_id);

SELECT (SELECT count(*) FROM healthcare_dev.deid.patient)   AS patients,
       (SELECT count(*) FROM healthcare_dev.deid.encounter) AS encounters,
       (SELECT count(*) FROM healthcare_dev.deid.note)      AS notes;
