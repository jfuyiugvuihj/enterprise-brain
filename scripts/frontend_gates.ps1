param(
    [string]$RepoDir = (Join-Path $PSScriptRoot '..'),
    [string[]]$Gates = @('lockfile', 'test', 'lint', 'colors', 'build')
)
# Run every frontend gate from one place so no line has to remember five commands.
$ErrorActionPreference = 'Continue'
$repo = (Resolve-Path -LiteralPath $RepoDir).Path
$fe = Join-Path $repo 'frontend'
if (-not (Test-Path -LiteralPath (Join-Path $fe 'package.json'))) {
    Write-Host "no frontend/package.json under $repo"
    exit 3
}
$results = [ordered]@{}
foreach ($g in $Gates) {
    Write-Host ""
    Write-Host "=== gate $g"
    switch ($g) {
        'lockfile' { & node (Join-Path $PSScriptRoot 'check_lockfile_sync.mjs') $fe }
        'test'    { Push-Location $fe; & npm run test; Pop-Location }
        'lint'    { Push-Location $fe; & npm run lint; Pop-Location }
        'colors'  { Push-Location $fe; & npm run lint:colors; Pop-Location }
        'build'   { Push-Location $fe; & npm run build; Pop-Location }
        default   { Write-Host "unknown gate: $g" }
    }
    $results[$g] = $LASTEXITCODE
}
Write-Host ""
Write-Host "=== gate summary (0 = pass)"
$results.GetEnumerator() | ForEach-Object { '  {0,-9} {1}' -f $_.Key, $_.Value }
if (@($results.Values | Where-Object { $_ -ne 0 }).Count -gt 0) { exit 1 }
exit 0
