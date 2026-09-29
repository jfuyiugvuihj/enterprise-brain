# Fix the recurring Docker Desktop startup failure on this workstation.
#
#   starting services: initializing Ingest server: listening on unix://.../Docker/run/sailor-ingest.sock:
#   rename ...\sailor-ingest.sock ...\sailor-ingest.sock.stale: The file cannot be accessed by the system.
#
# Root cause: an AF_UNIX socket left behind by a crashed Docker Desktop cannot be renamed to
# *.stale by the service, so the listener never starts and the whole app dies. Renaming the
# containing directory out of the way is enough; deleting anything is not required and is not
# done here. This script NEVER deletes. It renames, and every rename is reversible.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/fix_docker_stale_socket.ps1            # simulate, touches nothing
#   powershell -ExecutionPolicy Bypass -File scripts/fix_docker_stale_socket.ps1 -Apply     # stop, rename, restart
#   powershell -ExecutionPolicy Bypass -File scripts/fix_docker_stale_socket.ps1 -Apply -Force
#
# -Apply without -Force refuses to run while the engine still answers 'docker version',
# because a working stack must not be torn down on the strength of an old error dialog.
param(
    [switch]$Apply,
    [switch]$Force,
    [string]$Stamp = (Get-Date -Format 'HHmm')
)

$ErrorActionPreference = 'Stop'
$runDir = Join-Path $env:LOCALAPPDATA 'Docker\run'
$secretDir = Join-Path $env:LOCALAPPDATA 'docker-secrets-engine'
$dockerCli = 'E:\Docker\Docker\resources\bin\docker.exe'
$desktopExe = 'E:\Docker\Docker\Docker Desktop.exe'
$processNames = @('Docker Desktop', 'com.docker.backend', 'com.docker.build', 'com.docker.proxy', 'docker-agent', 'docker-compose')

function Test-EngineAlive {
    if (-not (Test-Path $dockerCli)) { return $false }
    try {
        & $dockerCli version --format '{{.Server.Version}}' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$alive = Test-EngineAlive
Write-Output ('engine answers docker version : ' + $alive)
Write-Output ('run dir                        : ' + $runDir + '  exists=' + (Test-Path $runDir))
Write-Output ('secrets-engine dir             : ' + $secretDir + '  exists=' + (Test-Path $secretDir))

$targets = @()
foreach ($dir in @($runDir, $secretDir)) {
    if (Test-Path $dir) {
        $stale = @(Get-ChildItem -LiteralPath $dir -Force -Filter '*.stale' -ErrorAction SilentlyContinue)
        $socks = @(Get-ChildItem -LiteralPath $dir -Force -Filter '*.sock' -ErrorAction SilentlyContinue)
        Write-Output ('  ' + $dir + ' -> ' + $socks.Count + ' socket(s), ' + $stale.Count + ' *.stale leftover(s)')
        $targets += $dir
    }
}

if ($alive -and -not $Force) {
    Write-Output 'REFUSED: the engine is answering right now. Nothing is broken to fix.'
    Write-Output '         If Docker Desktop still shows the error dialog, click Close first,'
    Write-Output '         then re-run with -Apply -Force only if the next start fails again.'
    exit 0
}

if (-not $Apply) {
    Write-Output ''
    Write-Output 'SIMULATION - no process stopped, no directory renamed, nothing written.'
    Write-Output ('would stop   : ' + (($processNames | Where-Object { Get-Process -Name $_ -ErrorAction SilentlyContinue } | ForEach-Object { $_ }) -join ', '))
    foreach ($dir in $targets) {
        Write-Output ('would rename : ' + $dir + '  ->  ' + (Split-Path $dir -Leaf) + '.dead-' + $Stamp)
    }
    Write-Output ('would start  : ' + $desktopExe)
    Write-Output ''
    Write-Output 'Recovery afterwards: each renamed directory can be moved back with Rename-Item -LiteralPath.'
    Write-Output 'Add -Apply to actually do it.'
    exit 0
}

Write-Output ''
Write-Output 'APPLYING'
foreach ($name in $processNames) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Output ('stop   ' + $_.ProcessName + ' pid=' + $_.Id)
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 8

foreach ($dir in $targets) {
    $leaf = Split-Path $dir -Leaf
    $parent = Split-Path $dir -Parent
    $moved = Join-Path $parent ($leaf + '.dead-' + $Stamp)
    if (Test-Path $moved) { $moved = $moved + '-retry' + (Get-Date -Format 'ss') }
    Move-Item -LiteralPath $dir -Destination $moved
    Write-Output ('renamed ' + $dir + ' -> ' + $moved)
}

if (Test-Path $desktopExe) {
    Start-Process -FilePath $desktopExe -WindowStyle Hidden
    Write-Output 'started Docker Desktop; give it up to ~90 s, then check the stack:'
} else {
    Write-Output ('Docker Desktop not at ' + $desktopExe + ' - start it by hand and report where it lives.')
}
Write-Output ('  docker ps --format "{{.Names}}|{{.Status}}"')
Write-Output 'The compose stack normally comes back by itself. Do not rebuild any image for this.'
exit 0
