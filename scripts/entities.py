"""Canonical list of Synthea entities landed into bronze.

Deliberately duplicated in pipelines/medallion/bronze/bronze.py — that file
runs inside a Lakeflow pipeline where importing from the repo root is
version-dependent friction. Twelve strings is cheaper to duplicate than to
fight the import path. Keep the two lists in sync.
"""

ENTITIES: list[str] = [
    "patients",
    "encounters",
    "conditions",
    "medications",
    "observations",
    "procedures",
    "immunizations",
    "allergies",
    "careplans",
    "organizations",
    "providers",
    "payers",
]
