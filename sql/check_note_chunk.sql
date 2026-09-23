-- Phase 3b step 2 checks. Run with:
--   .venv/Scripts/python.exe -m scripts.run_sql sql/check_note_chunk.sql

-- 1. Shape. Expect ~193,000 pieces across 1,148 patients.
SELECT count(*) AS pieces,
       count(DISTINCT patient_id) AS patients,
       round(avg(length(chunk_text))) AS avg_piece_chars,
       max(length(chunk_text)) AS max_piece_chars
FROM healthcare_dev.silver.note_chunk;

-- 2. The check that matters: glue the pieces back and compare to the original.
--    Only the first 1800 characters of each piece are taken, so the 200-char
--    overlap is not counted twice. sort_array on a struct sorts by its first
--    field, which is why chunk_index is first.
WITH rebuilt AS (
    SELECT patient_id,
           concat_ws('', transform(
               sort_array(collect_list(struct(chunk_index, substring(chunk_text, 1, 1800)))),
               x -> x.col2)) AS joined
    FROM healthcare_dev.silver.note_chunk
    GROUP BY patient_id
)
SELECT count(*) AS patients_checked,
       sum(CASE WHEN n.note_text = r.joined THEN 1 ELSE 0 END) AS rebuilt_exactly,
       sum(CASE WHEN n.note_text <> r.joined THEN 1 ELSE 0 END) AS MISMATCHED
FROM rebuilt r JOIN healthcare_dev.bronze.br_notes n USING (patient_id);
