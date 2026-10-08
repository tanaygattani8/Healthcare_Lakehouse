-- Phase 3b step 1d — bring br_notes under the 3a governance.
--
-- _source_file is the note's filename, which looks like
-- Aaron_Botsford_<uuid>.txt. The patient's real name is in it, so it is
-- exactly as private as silver.patient.FIRST and gets the same treatment.
--
-- note_text is deliberately NOT tagged. It is the most PHI-dense column in
-- the whole lakehouse — a first name 89 times and 89 dates per note — and
-- masking it would make phase 3b impossible, because every detection program
-- has to read it. That is the honest trade: the notes stay readable because
-- measuring how well we can hide them is the point of the phase. What
-- protects them is that nothing derived from them is ever published; the
-- snapshot is counts only.

ALTER TABLE healthcare_dev.bronze.br_notes
  ALTER COLUMN _source_file SET TAGS ('phi_category' = 'name');

-- The bronze policy that covers this tag was first created here. It now
-- lives in governance_bronze.sql, which widened it to every tag value when
-- br_patients was tagged (D79). Run that file after this one.
