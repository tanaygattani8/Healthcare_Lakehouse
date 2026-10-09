-- Phase 3b step 2 checks: python -m scripts.run_sql sql/check_note_chunk.sql

-- 1. Shape. Expect ~193,000 pieces across 1,148 patients.
SELECT count(*) AS pieces,
       count(DISTINCT patient_id) AS patients,
       round(avg(length(chunk_text))) AS avg_piece_chars,
       max(length(chunk_text)) AS max_piece_chars
FROM healthcare_dev.silver.note_chunk;

-- 2. Glue each piece's first 1800 characters back together and compare to the original.
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
