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

-- The 3a policies are attached to silver and ops. bronze had none, so the tag
-- above would otherwise label a column as private and leave it in the clear —
-- which governance_check.sql is built to catch.
CREATE OR REPLACE POLICY mask_phi_text
  ON SCHEMA healthcare_dev.bronze
  COMMENT 'Redact names and identifier numbers for uncleared readers.'
  COLUMN MASK healthcare_dev.ops.mask_text
  TO `account users`
  FOR TABLES
  MATCH COLUMNS has_tag_value('phi_category', 'name')
             OR has_tag_value('phi_category', 'geography')
             OR has_tag_value('phi_category', 'ssn')
             OR has_tag_value('phi_category', 'license')
             OR has_tag_value('phi_category', 'other_id') AS c
  ON COLUMN c;
