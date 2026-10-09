-- Cut notes into 2,000-character pieces every 1,800, so a name on a boundary is whole in one.
-- char_start maps a piece's position back to the note's.

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
