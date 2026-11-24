$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$source = Join-Path $PSScriptRoot "fragevariator"
$manifest = Get-Content -Raw -LiteralPath (Join-Path $source "manifest.json") | ConvertFrom-Json
$version = $manifest.human_version
if ($version -notmatch '^\d+\.\d+\.\d+$') {
    throw "manifest.json must contain a version in major.minor.patch format."
}

$staging = Join-Path $PSScriptRoot "package-$version"
$outputs = Join-Path $workspace "outputs"
$zipPath = Join-Path $staging "Variator-$version.zip"
$addonPath = Join-Path $outputs "Variator-$version.ankiaddon"

if (Test-Path -LiteralPath $staging) {
    $previousStage = Get-Item -Force -LiteralPath $staging
    if ($previousStage.FullName -ne $staging -or
        -not $previousStage.PSIsContainer -or
        ($previousStage.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Unexpected staging folder: $staging"
    }
    Remove-Item -LiteralPath $previousStage.FullName -Recurse -Force
}
New-Item -ItemType Directory -Path $staging | Out-Null
New-Item -ItemType Directory -Path $outputs -Force | Out-Null

$include = @(
    "__init__.py",
    "addon.py",
    "anki_bridge.py",
    "deck_queue.py",
    "front_screenshot.py",
    "i18n.py",
    "live.py",
    "CHANGELOG.md",
    "config.json",
    "config.md",
    "LICENSE",
    "manifest.json",
    "README.md"
)
foreach ($name in $include) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination $staging
}

foreach ($moduleFolder in @("core", "ui")) {
    $destination = Join-Path $staging $moduleFolder
    New-Item -ItemType Directory -Path $destination | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $source $moduleFolder) -File -Filter "*.py" |
        Copy-Item -Destination $destination
}

$packageEntries = Get-ChildItem -LiteralPath $staging | Select-Object -ExpandProperty FullName
Compress-Archive -LiteralPath $packageEntries -DestinationPath $zipPath -CompressionLevel Optimal
Move-Item -LiteralPath $zipPath -Destination $addonPath -Force
Copy-Item -LiteralPath (Join-Path $source "README.md") -Destination (Join-Path $outputs "Variator-README.md") -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Variator-AnkiWeb-Listing.md") -Destination (Join-Path $outputs "Variator-AnkiWeb-Listing.md") -Force

Get-FileHash -Algorithm SHA256 -LiteralPath $addonPath
Get-Item -LiteralPath $addonPath
