param(
    [string]$Catalog = "healthcare_dev",
    [string]$OutputDir = "synthea/output"
)

# Keep in sync with scripts/entities.py. An entity missing here silently
# produces an empty bronze table. Enforced by tests/test_entity_lists_match.py.
$entities = @(
    "patients", "encounters", "conditions", "medications",
    "observations", "procedures", "immunizations", "allergies", "careplans",
    "organizations", "providers", "payers"
)

$target = "dbfs:/Volumes/$Catalog/bronze/landing/csv"

foreach ($entity in $entities) {
    $source = Join-Path $OutputDir "csv/$entity.csv"
    if (-not (Test-Path $source)) {
        Write-Host "Skipping $entity - not found."
        continue
    }

    # One directory per entity: Auto Loader watches directories, not files.
    # fs cp does not create intermediate directories; mkdir is idempotent.
    $dest = "$target/$entity"
    databricks fs mkdir "$dest"
    if ($LASTEXITCODE -ne 0) { throw "could not create $dest" }

    Write-Host "Uploading $entity..."
    databricks fs cp $source "$dest/$entity.csv" --overwrite
    # Without this, twelve failed uploads still end with "Done."
    if ($LASTEXITCODE -ne 0) { throw "upload failed for $entity" }
}

Write-Host "Done."