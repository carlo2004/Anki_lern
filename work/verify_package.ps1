$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$source = Join-Path $PSScriptRoot "fragevariator"
$manifest = Get-Content -Raw -LiteralPath (Join-Path $source "manifest.json") | ConvertFrom-Json
$version = $manifest.human_version
if ($version -notmatch '^\d+\.\d+\.\d+$') {
    throw "manifest.json must contain a version in major.minor.patch format."
}

$archive = Join-Path (Join-Path $workspace "outputs") "Variator-$version.ankiaddon"
$extract = Join-Path $PSScriptRoot "package-verify-$version"
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    throw "Build the package first: $archive"
}
if (Test-Path -LiteralPath $extract) {
    $previousExtract = Get-Item -Force -LiteralPath $extract
    if ($previousExtract.FullName -ne $extract -or
        -not $previousExtract.PSIsContainer -or
        ($previousExtract.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Unexpected verification folder: $extract"
    }
    Remove-Item -LiteralPath $previousExtract.FullName -Recurse -Force
}
[System.IO.Compression.ZipFile]::ExtractToDirectory($archive, $extract)

foreach ($name in @("manifest.json", "__init__.py", "config.json", "LICENSE")) {
    if (-not (Test-Path -LiteralPath (Join-Path $extract $name) -PathType Leaf)) {
        throw "Missing required package file: $name"
    }
}
foreach ($file in Get-ChildItem -LiteralPath $extract -Recurse -File) {
    $relativePath = [IO.Path]::GetRelativePath($extract, $file.FullName)
    $sourceFile = Join-Path $source $relativePath
    if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf) -or
        (Get-FileHash -LiteralPath $file.FullName).Hash -ne
        (Get-FileHash -LiteralPath $sourceFile).Hash) {
        throw "Package file differs from source: $relativePath"
    }
}

Write-Output $extract
