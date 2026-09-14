param(
    [switch]$Test
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\frontend")
if ($Test) {
    npm run test
} else {
    npm run build
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
