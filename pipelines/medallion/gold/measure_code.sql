-- Every care-gap code in one place (D57).

CREATE OR REFRESH MATERIALIZED VIEW ${catalog}.gold.measure_code
COMMENT "Every code the care-gap measures use. The one place they are defined."
TBLPROPERTIES ("quality" = "gold")
AS SELECT * FROM VALUES
    -- Diabetes complications too: the plain code covers only 79 patients.
    ('diabetes_hba1c', 'denominator', 'condition',  '44054006',        'Diabetes mellitus type 2'),
    ('diabetes_hba1c', 'denominator', 'condition',  '127013003',       'Disorder of kidney due to diabetes mellitus'),
    ('diabetes_hba1c', 'denominator', 'condition',  '90781000119102',  'Microalbuminuria due to type 2 diabetes mellitus'),
    ('diabetes_hba1c', 'denominator', 'condition',  '157141000119108', 'Proteinuria due to type 2 diabetes mellitus'),
    ('diabetes_hba1c', 'denominator', 'condition',  '1551000119108',   'Nonproliferative diabetic retinopathy due to type II diabetes mellitus'),
    ('diabetes_hba1c', 'denominator', 'condition',  '368581000119106', 'Neuropathy due to type 2 diabetes mellitus'),
    ('diabetes_hba1c', 'denominator', 'condition',  '97331000119101',  'Macular edema and retinopathy due to type 2 diabetes mellitus'),
    ('diabetes_hba1c', 'denominator', 'condition',  '1501000119109',   'Proliferative diabetic retinopathy due to type II diabetes mellitus'),
    ('diabetes_hba1c', 'numerator',   'observation', '4548-4',         'Hemoglobin A1c'),
    ('bp_control',     'denominator', 'condition',  '59621000',        'Essential hypertension'),
    ('bp_control',     'numerator',   'observation', '8480-6',         'Systolic blood pressure'),
    ('bp_control',     'numerator',   'observation', '8462-4',         'Diastolic blood pressure'),
    -- Heart disease: 53741008 (coronary heart disease) has 0 patients here.
    ('statin_therapy', 'denominator', 'condition',  '414545008',       'Ischemic heart disease'),
    ('statin_therapy', 'denominator', 'condition',  '399261000',       'History of coronary artery bypass grafting'),
    ('statin_therapy', 'denominator', 'condition',  '22298006',        'Myocardial infarction'),
    ('statin_therapy', 'denominator', 'condition',  '399211009',       'History of myocardial infarction'),
    ('statin_therapy', 'denominator', 'condition',  '401303003',       'Acute ST segment elevation myocardial infarction'),
    ('statin_therapy', 'denominator', 'condition',  '401314000',       'Acute non-ST segment elevation myocardial infarction'),
    ('statin_therapy', 'denominator', 'condition',  '230690007',       'Stroke'),
    -- Whole words: 'nystatin' is an antifungal (D57).
    ('statin_therapy', 'numerator',   'medication', 'simvastatin',     'statin'),
    ('statin_therapy', 'numerator',   'medication', 'atorvastatin',    'statin'),
    ('statin_therapy', 'numerator',   'medication', 'rosuvastatin',    'statin'),
    ('statin_therapy', 'numerator',   'medication', 'pravastatin',     'statin'),
    ('statin_therapy', 'numerator',   'medication', 'lovastatin',      'statin'),
    ('statin_therapy', 'numerator',   'medication', 'fluvastatin',     'statin'),
    ('statin_therapy', 'numerator',   'medication', 'pitavastatin',    'statin')
AS t(measure, role, source, code, label);
