param(
    [string]$Destination = 'D:\Lap trinh\Đồ án tốt nghiệp\Ứng dụng'
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path $PSScriptRoot -Parent
$Parent = (Resolve-Path -LiteralPath $Destination).Path
$Folder = Join-Path $Parent 'ohayo-smartlms'
$Archive = Join-Path $Parent 'ohayo-smartlms.zip'
if ((Test-Path -LiteralPath $Folder) -or (Test-Path -LiteralPath $Archive)) {
    throw 'Package folder or ZIP already exists. Refusing to overwrite existing data.'
}

$Files = @(
    'backend/apps/__init__.py',
    'backend/apps/ai/__init__.py',
    'backend/requirements-embedding.txt',
    'scripts/build_sample_index.py',
    'scripts/check_index_reload.py',
    'scripts/check_scoped_retrieval.py',
    'scripts/evaluate_retrieval.py',
    'data/fixtures/w3-sample-chunks.json',
    'data/fixtures/w3-evaluation-qa.json',
    'data/fixtures/w3-evaluation-predictions.json',
    'data/qa/qa_pilot_v2.0.csv',
    'data/qa/qa_pilot_v2.0_review.csv',
    'data/qa/qa_pilot_v2.0_additions.json',
    'data/qa/qa_pilot_v2.0_corrections.json'
)
foreach ($Module in @('embeddings', 'retrieval', 'evaluation', 'tests')) {
    $Directory = Join-Path $Repo "backend/apps/ai/$Module"
    foreach ($File in Get-ChildItem -LiteralPath $Directory -File -Filter '*.py') {
        $Files += "backend/apps/ai/$Module/$($File.Name)"
    }
}
$Files += 'backend/apps/ai/embeddings/config.json'
$Files = @($Files | Sort-Object -Unique)
foreach ($Relative in $Files) {
    if (-not (Test-Path -LiteralPath (Join-Path $Repo $Relative) -PathType Leaf)) {
        throw "Missing source file: $Relative"
    }
}
$Readme = Join-Path $Repo 'docs/kaggle-package-readme.md'
if (-not (Test-Path -LiteralPath $Readme -PathType Leaf)) { throw 'Missing README source.' }

New-Item -ItemType Directory -Path $Folder | Out-Null
$Entries = @()
foreach ($Relative in $Files) {
    $Source = Join-Path $Repo $Relative
    $Target = Join-Path $Folder $Relative
    New-Item -ItemType Directory -Path (Split-Path $Target -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Target
    $Hash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Hash -ne (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()) {
        throw "Copy checksum mismatch: $Relative"
    }
    $Entries += [ordered]@{ path = $Relative; sha256 = $Hash }
}
Copy-Item -LiteralPath $Readme -Destination (Join-Path $Folder 'README.md')
$Entries += [ordered]@{ path = 'README.md'; sha256 = (Get-FileHash -LiteralPath $Readme -Algorithm SHA256).Hash.ToLowerInvariant() }
$Manifest = [ordered]@{
    package = 'ohayo-smartlms'
    prepared_date = '2026-10-15'
    purpose = 'Kaggle W3 sample workspace; not final corpus evaluation'
    source_commit = (& git -C $Repo rev-parse HEAD)
    working_copy_files = $true
    files = $Entries
}
$Manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Folder 'package-manifest.json') -Encoding utf8
Compress-Archive -LiteralPath $Folder -DestinationPath $Archive -CompressionLevel Optimal
[ordered]@{
    folder = $Folder
    archive = $Archive
    file_count = $Entries.Count + 1
    archive_bytes = (Get-Item -LiteralPath $Archive).Length
    archive_sha256 = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json
