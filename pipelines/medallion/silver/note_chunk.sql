-- Cut every note into overlapping pieces small enough to hand to a model.
--
-- The longest note is 3.6 million characters. Nothing reads that in one go, so
-- cutting is forced rather than an optimisation.
--
-- Move forward 1800 characters each step but take 2000, so every pair of
-- neighbours shares 200 characters. A name landing on a boundary is therefore
-- whole in at least one piece. 200 is far longer than any name or date here.
--
-- char_start is the column that makes the rest of the phase possible. A
-- program reports "found a name at position 50" — of a piece that began at
-- 21,600, so the real position is 21,650. Without this, nothing a detector
-- says can be compared to the answer key at all.
--
-- Pieces overlap, so the same name is found twice in the shared region. That
-- is handled at scoring time by matching on absolute position, not here.

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.silver.note_chunk
COMMENT "Notes cut into overlapping 2000-character pieces, with their position in the original."
TBLPROPERTIES ("quality" = "silver")
AS
SELECT
    n.patient_id,
    piece.idx                                                 AS chunk_index,
    (piece.idx - 1) * 1800                                    AS char_start,
    -- substring is 1-based, so +1. Past the end it simply returns less.
    substring(n.note_text, (piece.idx - 1) * 1800 + 1, 2000)  AS chunk_text
FROM ${catalog}.bronze.br_notes n
LATERAL VIEW explode(
    -- how many 1800-character steps are needed to cover this note
    sequence(1, greatest(1, cast(ceil(length(n.note_text) / 1800.0) AS INT)))
) piece AS idx;
