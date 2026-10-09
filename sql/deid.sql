-- Phase 3b step 6: the de-identified copy; gold keeps reading real silver (D55).
-- Names, identifiers, address, coordinates, birthplace, file names: dropped; [NAME] in notes.
-- Birth and death dates: 5-year band, blank when k < 5 or age 90+ (D56).
-- ZIP: dropped; even 3 digits left 471 of 1,148 people alone (D56).
-- Visit and note dates: one random shift per patient, gaps kept; not Safe Harbor.
-- patient_id: replaced by a random deid_id.

-- The secrets: a random id and shift per patient, drawn once; ops only, never deid.
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

-- Replace spans from the end so positions stay valid; overlaps keep the first, longest.
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
COMMENT "De-identified patients. 5-year birth and death bands, blank where fewer than 5 people share band + gender + death band, and for 90+. No ZIP, names, identifiers, income or spend. Join on deid_id."
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
-- Bands blanked when fewer than 5 people share them (D56).
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
       MARITAL AS marital, STATE AS state
-- No income or spend: near-unique per person (D56, D81).
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
COMMENT "De-identified notes. Private text found by the patient's own details (the answer sheet's spans, so no score; check_deid finds no first name left) replaced: [NAME], dates moved by the patient's shift, 90+."
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
