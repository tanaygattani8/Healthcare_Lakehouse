# Synthea generation

## Dev tier — regenerate with

```
java -jar synthea/synthea-with-dependencies.jar \
  -c synthea/synthea.properties \
  -p 1000 -s 12345 -cs 12345 -r 20260101 -e 20260808 \
  Massachusetts
```

`-e 20260808` was **not** in the original command. Without it Synthea simulates
up to the day it runs, so the same seeds give a different dataset every day
(errors.md E31). 20260808 is the day the recorded dataset was generated, read
from its `metadata/*.json`.

Requires **Java 17 or higher**. The jar is compiled to class file version 61;
an older JDK fails with `UnsupportedClassVersionError`. Built here with
Temurin 21.0.12 LTS.

| Parameter | Value | Why |
|---|---|---|
| Population | 1000 | Dev tier. Fast iteration, negligible quota use. |
| Population seed `-s` | 12345 | Reproducibility |
| Clinician seed `-cs` | 12345 | Reproducibility |
| Reference date `-r` | 20260101 | Without a fixed reference date the dataset shifts every run |
| End date `-e` | 20260808 | Without it the simulation runs to today, and the dataset shifts every day |
| State | Massachusetts | Single state keeps geography simple for phase 3 ZIP suppression |

All four are required together. Output is gitignored — the jar is too
(188 MB).

## Or with Docker — no local Java, and no jar to find

The jar used above was Synthea's rolling `master-branch-latest` build, since
overwritten, so it cannot be downloaded again. The image builds the same code
from its permanent commit, `7e08387` (decision.md D35):

```
docker build -t healthcare-synthea:7e08387 synthea/
docker run --rm -v C:\synthea-test:/data healthcare-synthea:7e08387
```

**It reproduces the dataset's shape, not the exact dataset.** Same code, config
and seeds; 861 of 1,148 patients come out identical, totals ~0.2% off. Cause
not yet identified — decision.md D35.

Output lands in `C:\synthea-test\synthea\output\`. Mount a scratch directory,
never `synthea/output/` — a wrong image would overwrite the only copy of the
dataset `calibration.md` describes. The seeds, reference date and properties
file are baked into the image.

Build one image at a time on an 8 GB machine (errors.md E27).

## Result of the recorded run

```
Records: total=1148, alive=1000, dead=148
```

`-p 1000` requests 1,000 **living** patients; deceased patients are generated
in addition. A count of exactly 1,000 would mean `generate.only_alive_patients`
had been flipped on, which would bias every downstream mortality and
readmission figure.

| Output | Count |
|---|---|
| Patients | 1,148 |
| Clinical notes | 1,148 |
| CSV files | 18 |
| Inpatient encounters | 1,292 |

## Overridden defaults, and why each matters

| Property | Default | Set to | Consequence if left at default |
|---|---|---|---|
| `exporter.clinical_note.export` | `false` | `true` | No notes at all. Phase 3's de-identification work has nothing to run on. |
| `exporter.years_of_history` | `10` | `0` | History truncated to 10 years. Readmission analysis needs the complete encounter record. |
| `generate.append_numbers_to_person_names` | `true` | `false` | Names generate as `Abdul218`. A two-character regex would then score near-perfect F1 on name detection, making phase 3's headline metric meaningless. |

**If this dataset is ever regenerated, check all three.** The third is the one
that fails silently — everything still runs, the numbers just stop meaning
anything.

## Smoke test before a full run

A full run takes well over ten minutes. Three patients into a disposable
directory takes seconds and catches config mistakes:

```
java -jar synthea/synthea-with-dependencies.jar \
  -c synthea/synthea.properties \
  --exporter.baseDirectory ./synthea/smoke/ \
  -p 3 -s 1 -cs 1 -r 20260101 Massachusetts
```

Check `csv`, `fhir`, `metadata` and `notes` all appear, and that names in
`patients.csv` carry no trailing digits. Then delete `synthea/smoke/`.
