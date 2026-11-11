[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,
    [string]$PgRoot = "C:\Program Files\PostgreSQL\16",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$source = (Resolve-Path -LiteralPath $SourceDir).Path
$library = Join-Path $PgRoot "lib"
$extension = Join-Path $PgRoot "share\extension"
$dll = Join-Path $source "vector.dll"
$control = Join-Path $source "vector.control"
$sqlDirectory = Join-Path $source "sql"
$sqlFiles = Get-ChildItem -LiteralPath $sqlDirectory -Filter "vector--*.sql" -File

if (-not (Test-Path -LiteralPath $dll)) {
    throw "Missing compiled extension library: $dll"
}
if (-not (Test-Path -LiteralPath $control) -or $sqlFiles.Count -eq 0) {
    throw "Missing pgvector control or SQL files in $source"
}
if (-not (Test-Path -LiteralPath $library) -or -not (Test-Path -LiteralPath $extension)) {
    throw "PostgreSQL extension directories were not found under $PgRoot"
}

$existing = @(
    (Join-Path $library "vector.dll"),
    (Join-Path $extension "vector.control")
) | Where-Object { Test-Path -LiteralPath $_ }
if ($existing.Count -gt 0 -and -not $Force) {
    throw "PGVector is already installed. Use -Force only after an explicit upgrade review."
}

Copy-Item -LiteralPath $dll -Destination $library -Force:$Force
Copy-Item -LiteralPath $control -Destination $extension -Force:$Force
foreach ($sqlFile in $sqlFiles) {
    Copy-Item -LiteralPath $sqlFile.FullName -Destination $extension -Force:$Force
}

Write-Output "Installed PGVector files: dll=1 control=1 sql=$($sqlFiles.Count)"
