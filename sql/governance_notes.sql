-- Phase 3b: _source_file holds the patient's name; note_text stays untagged so detection can read it.

ALTER TABLE healthcare_dev.bronze.br_notes
  ALTER COLUMN _source_file SET TAGS ('phi_category' = 'name');

-- The bronze policy now lives in governance_bronze.sql (D79); run it after this.
