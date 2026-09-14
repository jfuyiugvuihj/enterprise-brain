<#
.SYNOPSIS
  Start the isolated PostgreSQL 16 + PGVector acceptance cluster on 127.0.0.1:5433.
.DESCRIPTION
  The cluster lives in tmp/pgvector-isolated-5433 and is a plain process, not a Windows
  service, so it does not survive a reboot. The shared 5432 service is untouched.
  The superuser password stays in tmp/pgvector-isolated-5433.secret (DPAPI SecureString)
  and is only ever placed into this process's environment, never printed.
#>
param(
    [string]$BinDir = 'C:\Program Files\PostgreSQL\16\bin',
    [int]$Port = 5433
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $root "tmp\pgvector-isolated-$Port"
$secret = Join-Path $root "tmp\pgvector-isolated-$Port.secret"
if (-not (Test-Path (Join-Path $data 'PG_VERSION'))) { throw "no cluster at $data" }
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    Write-Output "isolated PostgreSQL already listening on $Port"
    exit 0
}
$pgctl = Join-Path $BinDir 'pg_ctl.exe'
$psql = Join-Path $BinDir 'psql.exe'
if (-not (Test-Path $pgctl)) { throw "pg_ctl.exe not found under $BinDir (set -BinDir)" }
# A stale postmaster.pid is normal after a hard reboot; pg_ctl refuses to start while the
# recorded process still looks alive, so report it instead of waiting forever.
$logfile = Join-Path $data 'restart.log'
& $pgctl -D $data -o "-p $Port -h 127.0.0.1" -l $logfile -w -t 60 start
$started = $LASTEXITCODE
if ($started -ne 0) {
    Get-Content $logfile -Tail 15 -ErrorAction SilentlyContinue
    throw "pg_ctl start failed with exit code $started (see $logfile)"
}
if (-not (Test-Path $secret)) { throw "password file missing: $secret (verification skipped)" }
$secure = Get-Content $secret -Raw | ConvertTo-SecureString
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
try {
    & $psql -h 127.0.0.1 -p $Port -U postgres -d postgres -Atc 'select 1'
    if ($LASTEXITCODE -ne 0) { throw "verification query failed" }
    Write-Output "isolated PostgreSQL started on 127.0.0.1:$Port"
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}