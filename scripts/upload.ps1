param(
    [string]$Catalog = "healthcare_dev",
    [string]$OutputDir = "synthea/output"
)

# Keep in sync with scripts/entities.py — bronze builds one streaming table per
# entity from that list, so an entity missing here produces an empty table two
# tasks later and looks like an Auto Loader problem.
$entities = @(
    "patients", "encounters", "conditions", "medications",
    "observations", "procedures", "immunizations", "allergies", "careplans",
    "organizations", "providers", "payers"
)

$target = "dbfs:/Volumes/$Catalog/bronze/landing/csv"

# fs cp does not create intermediate directories, and the volume ships empty.
# mkdir is idempotent, so this is safe on every run.
databricks fs mkdir "$target"
if ($LASTEXITCODE -ne 0) { throw "could not create $target" }

foreach ($entity in $entities) {
    $source = Join-Path $OutputDir "csv/$entity.csv"
    if (-not (Test-Path $source)) {
        Write-Host "Skipping $entity - not found."
        continue
    }

    Write-Host "Uploading $entity..."
    databricks fs cp $source "$target/$entity.csv" --overwrite
    # Without this the script prints every error and still ends with "Done.",
    # which is how a fully failed upload gets mistaken for a successful one.
    if ($LASTEXITCODE -ne 0) { throw "upload failed for $entity" }
}

Write-Host "Done."