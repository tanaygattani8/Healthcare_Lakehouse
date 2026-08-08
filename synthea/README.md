# Synthea generation

## Dev tier — regenerate with

```
java -jar synthea/synthea-with-dependencies.jar \
  -c synthea/synthea.properties \
  -p 1000 -s 12345 -cs 12345 -r 20260101 \
  Massachusetts
```

Requires **Java 17 or higher**. The jar is compiled to class file version 61;
an older JDK fails with `UnsupportedClassVersionError`. Built here with
Temurin 21.0.12 LTS.

| Parameter | Value | Why |
|---|---|---|
| Population | 1000 | Dev tier. Fast iteration, negligible quota use. |
| Population seed `-s` | 12345 | Reproducibility |
| Clinician seed `-cs` | 12345 | Reproducibility |
| Reference date `-r` | 20260101 | Without a fixed reference date the dataset shifts every run |
| State | Massachusetts | Single state keeps geography simple for phase 3 ZIP suppression |

All three seeds are required together. Output is gitignored — the jar is too
(188 MB).

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
