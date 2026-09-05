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

foreach ($entity in $entities) {
    $source = Join-Path $OutputDir "csv/$entity.csv"
    if (-not (Test-Path $source)) {
        Write-Host "Skipping $entity - not found."
        continue
    }

    # One directory per entity. Auto Loader watches a directory, not a file, and
    # a shared directory would mean all twelve streams ingesting all twelve
    # files. fs cp does not create intermediate directories; mkdir is idempotent
    # so this is safe on every run.
    $dest = "$target/$entity"
    databricks fs mkdir "$dest"
    if ($LASTEXITCODE -ne 0) { throw "could not create $dest" }

    Write-Host "Uploading $entity..."
    databricks fs cp $source "$dest/$entity.csv" --overwrite
    # Without this the script prints every error and still ends with "Done.",
    # which is how a fully failed upload gets mistaken for a successful one.
    if ($LASTEXITCODE -ne 0) { throw "upload failed for $entity" }
}

Write-Host "Done."