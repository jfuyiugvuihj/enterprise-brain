# docker_up.ps1 -- Docker Desktop recovery launcher for this workstation.
#
# Why this file exists (2026-10-05, owner-reported repeat failure "每次重启都失败"):
#   Docker Desktop dies at "starting services: initializing Ingest server / Secrets Engine"
#   with "rename <name>.sock <name>.sock.stale: The file cannot be accessed by the system".
#   Root cause measured on this box: a zombie com.docker.backend from the previous crashed
#   run still holds the live unix socket, so the rename target cannot be created. The install
#   living on E: is NOT the cause -- so the exe path is *derived*, never hardcoded.
#
# Remedy (in order, idempotent): derive exe path -> kill orphan docker procs -> clear the
# zero-byte socket leftovers if Windows lets us (they are usually undeletable tombstones and
# that is harmless) -> wsl --shutdown -> start -> wait for the npipe -> verify server.
#
# Usage:
#   powershell -NoProfile -File scripts\docker_up.ps1
#   powershell -NoProfile -File scripts\docker_up.ps1 -ComposeUp
param(
    [int]$WaitSeconds = 240,
    [switch]$ComposeUp,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$pipe = "\\.\pipe\dockerDesktopLinuxEngine"

function Get-DockerExe {
    $found = @()
    $cmd = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        $bin = Split-Path $cmd.Source
        if ((Split-Path $bin -Leaf) -eq "bin") {
            $root = Split-Path (Split-Path $bin -Parent) -Parent
            $found += (Join-Path $root "Docker Desktop.exe")
        }
    }
    foreach ($k in "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                  "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*") {
        Get-ItemProperty $k -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like "*Docker Desktop*" } |
            ForEach-Object { if ($_.InstallLocation) { $found += (Join-Path $_.InstallLocation "Docker Desktop.exe") } }
    }
    $found += "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    $found += "E:\Docker\Docker\Docker Desktop.exe"
    foreach ($f in $found) { if (Test-Path -LiteralPath $f) { return $f } }
    throw "Docker Desktop.exe not found. Looked in: $($found -join ' | ')"
}

function Test-Pipe { return [System.IO.File]::Exists($pipe) }

function Stop-Orphans {
    $names = @("com.docker.backend", "com.docker.build", "com.docker.proxy", "Docker Desktop")
    $running = Get-Process $names -ErrorAction SilentlyContinue
    if (-not $running) { return 0 }
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    return $running.Count
}

function Clear-SocketLeftovers {
    $roots = @((Join-Path $env:LOCALAPPDATA "Docker\run"),
               (Join-Path $env:LOCALAPPDATA "docker-secrets-engine"))
    $deleted = New-Object System.Collections.Generic.List[string]
    $kept = New-Object System.Collections.Generic.List[string]
    foreach ($r in $roots) {
        if (-not (Test-Path -LiteralPath $r)) { continue }
        foreach ($f in (Get-ChildItem -LiteralPath $r -Force -File -ErrorAction SilentlyContinue)) {
            if ($f.Name -notlike "*.stale" -and $f.Name -notlike "*.sock") { continue }
            try {
                Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop
                $deleted.Add($f.Name)
            } catch {
                $kept.Add($f.Name)
            }
        }
    }
    return @{ Deleted = $deleted; Kept = $kept }
}

if (Test-Pipe) {
    Write-Output "ALREADY_UP $pipe"
} else {
    $exe = Get-DockerExe
    Write-Output "EXE $exe"
    Write-Output "ORPHANS_KILLED $(Stop-Orphans)"
    $sock = Clear-SocketLeftovers
    Write-Output "SOCKET_DELETED $($sock.Deleted.Count) / SOCKET_KEPT_TOMBSTONE $($sock.Kept.Count)"
    if ($DryRun) { Write-Output "DRYRUN_STOP"; exit 0 }
    wsl --shutdown 2>&1 | Out-Null
    Write-Output "WSL_SHUTDOWN_DONE"
    Start-Process -FilePath $exe -WindowStyle Hidden
    Write-Output "START_ISSUED $(Get-Date -Format s)"
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Pipe) { break }
        Start-Sleep -Milliseconds 1500
    }
    if (-not (Test-Pipe)) { Write-Output "FAILED pipe still absent after $WaitSeconds s"; exit 1 }
    Write-Output "PIPE_UP $(Get-Date -Format s)"
}
if ($DryRun) { Write-Output "DRYRUN_STOP"; exit 0 }
$ver = ""
$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
    $ver = docker version --format "{{.Server.Version}}" 2>&1
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 3
}
Write-Output "SERVER $ver rc=$LASTEXITCODE"
if ($ComposeUp) {
    Set-Location (Split-Path $PSScriptRoot -Parent)
    docker compose --env-file deploy\.env.server up -d 2>&1 | ForEach-Object { Write-Output $_ }
    Write-Output "COMPOSE_RC $LASTEXITCODE"
}
docker ps --format "{{.Names}} {{.Status}}" 2>&1 | ForEach-Object { Write-Output $_ }