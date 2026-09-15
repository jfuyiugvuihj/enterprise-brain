param(
    [switch]$Test,
    [switch]$SkipLockCheck
)

$ErrorActionPreference = "Stop"
$fe = Join-Path $PSScriptRoot "..\frontend"
Set-Location $fe

# G5 lockfile gate. `frontend/Dockerfile` runs `npm ci`, and the production install step is
# `docker compose --env-file deploy/.env.server build frontend` (deploy/README.server.md), so a
# declared-range drift between package.json and package-lock.json breaks the install, not just lint.
# We check the drift ourselves instead of calling `npm ci`, because on this host `npm ci` also fails
# on transitive platform-optional deps (@emnapi/*) for reasons unrelated to any commit.
if (-not $SkipLockCheck) {
    node (Join-Path $PSScriptRoot "check_lockfile_sync.mjs") $fe
    if ($LASTEXITCODE -ne 0) {
        "G5 lockfile gate FAILED. Align the two files with npm install and commit the refreshed"
        "lockfile (owner: whichever line touched the dependency). Bypass: -SkipLockCheck"
        exit $LASTEXITCODE
    }
}

if ($Test) {
    npm run test
} else {
    npm run build
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
