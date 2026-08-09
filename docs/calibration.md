# Calibration — dev tier

Patients generated: **1,148**

| File | Rows | Rows per patient | CSV bytes | Parquet bytes | Distinct codes |
|---|---:|---:|---:|---:|---:|
| observations.csv | 2,223,785 | 1937.1 | 382,167,216 | 13,561,312 | 282 |
| procedures.csv | 575,050 | 500.9 | 130,614,622 | 13,735,282 | 380 |
| encounters.csv | 187,540 | 163.4 | 62,340,474 | 9,860,059 | 56 |
| conditions.csv | 111,881 | 97.5 | 17,833,488 | 3,001,169 | 271 |
| medications.csv | 102,487 | 89.3 | 27,068,565 | 4,193,620 | 269 |
| immunizations.csv | 62,120 | 54.1 | 8,583,685 | 1,635,861 | 22 |
| careplans.csv | 10,357 | 9.0 | 2,062,129 | 659,100 | 38 |
| patients.csv | 1,148 | 1.0 | 335,296 | 175,549 | 0 |
| allergies.csv | 1,018 | 0.9 | 184,738 | 29,451 | 22 |
| organizations.csv | 826 | 0.7 | 130,550 | 89,411 | 0 |
| providers.csv | 826 | 0.7 | 151,193 | 109,631 | 0 |
| payers.csv | 10 | 0.0 | 1,875 | 4,211 | 0 |

**Total rows:** 3,277,048  
**Total CSV bytes:** 631,473,831  
**Total Parquet bytes:** 47,054,656

## Clinical notes

Notes: **1,148**, **384,624,701** bytes on disk.  
Length in characters — mean **335,034**, max **3,620,548**.

Note bytes are *not* included in the totals above. Phase 3 reads this
corpus in full, so add it to any quota estimate. Size the de-identification
context window from the max, not the mean.

## Extrapolation to the main tier

Multiply *rows per patient* by the target population. Size storage from
the **Parquet** column, not the CSV one — Delta stores Parquet. Check the
result against the Free Edition quota **before** generating it: exceeding
quota shuts down workspace compute for the rest of the day.
