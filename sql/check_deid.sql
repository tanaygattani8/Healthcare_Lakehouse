-- Phase 3b step 6 — does the de-identified copy hold? Every number marked
-- "must be 0" is a failure if it is not. Counts only.

-- One key per patient. The build inserts only missing patients, so a rerun
-- must not add a second shift — two shifts would break the timing check.
SELECT count(*) AS patients, count(DISTINCT patient_id) AS keyed,
       count(*) - count(DISTINCT patient_id) AS duplicate_keys_must_be_0,
       min(offset_days) AS min_shift, max(offset_days) AS max_shift
FROM healthcare_dev.ops.deid_key;

SELECT (SELECT count(*) FROM healthcare_dev.deid.patient)   AS patients,
       (SELECT count(*) FROM healthcare_dev.deid.encounter) AS encounters,
       (SELECT count(*) FROM healthcare_dev.silver.encounter) AS encounters_in_silver,
       (SELECT count(*) FROM healthcare_dev.deid.note)      AS notes;

-- Timing. The plan compared only first-to-last span per patient, which a
-- per-row shift could pass by luck. This compares every gap between
-- consecutive visits, in order.
WITH before AS (
    SELECT k.deid_id,
           array_sort(collect_list(e.started_at)) AS ts
    FROM healthcare_dev.silver.encounter e
    JOIN healthcare_dev.ops.deid_key k USING (patient_id)
    GROUP BY k.deid_id
),
after AS (
    SELECT deid_id, array_sort(collect_list(started_at)) AS ts
    FROM healthcare_dev.deid.encounter GROUP BY deid_id
),
gaps AS (
    SELECT b.deid_id,
           transform(sequence(2, greatest(size(b.ts), 2)),
                     i -> unix_timestamp(b.ts[i - 1]) - unix_timestamp(b.ts[i - 2])) AS gb,
           transform(sequence(2, greatest(size(a.ts), 2)),
                     i -> unix_timestamp(a.ts[i - 1]) - unix_timestamp(a.ts[i - 2])) AS ga
    FROM before b JOIN after a USING (deid_id)
)
SELECT count(*) AS patients_compared,
       sum(CASE WHEN gb <> ga THEN 1 ELSE 0 END) AS patients_whose_timing_changed_must_be_0
FROM gaps;

-- Names left in notes. The patient's first name, as a whole word, anywhere in
-- their de-identified note.
SELECT count(*) AS notes_checked,
       sum(CASE WHEN d.note_text RLIKE concat('(?<![A-Za-z])', p.FIRST, '(?![A-Za-z])')
                THEN 1 ELSE 0 END) AS notes_still_naming_patient_must_be_0,
       sum(CASE WHEN d.note_text LIKE '%[NAME]%' THEN 1 ELSE 0 END) AS notes_with_name_removed
FROM healthcare_dev.deid.note d
JOIN healthcare_dev.ops.deid_key k USING (deid_id)
JOIN healthcare_dev.silver.patient p USING (patient_id);

-- Dates moved, not lost: the same number of dates per note before and after.
WITH counts AS (
    SELECT k.deid_id,
           size(regexp_extract_all(n.note_text, '\\d{4}-\\d{2}-\\d{2}', 0)) AS dates_before
    FROM healthcare_dev.bronze.br_notes n
    JOIN healthcare_dev.ops.deid_key k USING (patient_id)
)
SELECT sum(c.dates_before) AS dates_before,
       sum(size(regexp_extract_all(d.note_text, '\\d{4}-\\d{2}-\\d{2}', 0))) AS dates_after,
       sum(CASE WHEN c.dates_before
                     <> size(regexp_extract_all(d.note_text, '\\d{4}-\\d{2}-\\d{2}', 0))
                THEN 1 ELSE 0 END) AS notes_with_dates_lost_must_be_0
FROM counts c JOIN healthcare_dev.deid.note d USING (deid_id);
