# ============================================================
# 企业智脑 — Windows 多实例启动脚本 (Layer 4)
# 用法: .\deploy\start_workers.ps1 -Workers 3 -BasePort 8001
# ============================================================

param(
    [int]$Workers = 3,
    [int]$BasePort = 8001
)

$App = "app.main:app"

Write-Host "=== 企业智脑 — 启动 $Workers 个 uvicorn 实例 ===" -ForegroundColor Green

# 停掉旧进程
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "uvicorn" -or $_.MainWindowTitle -match "uvicorn"
} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 确保日志目录存在
New-Item -ItemType Directory -Force -Path "logs" | Out-Null

for ($i = 0; $i -lt $Workers; $i++) {
    $Port = $BasePort + $i
    $LogFile = "logs/uvicorn_${Port}.log"

    Write-Host "  实例 #$($i+1) 端口 ${Port} ..." -ForegroundColor Cyan

    $env:PYTHONUNBUFFERED = 1
    Start-Process -NoNewWindow -FilePath "python" -ArgumentList @(
        "-m", "uvicorn", $App,
        "--host", "0.0.0.0",
        "--port", "$Port",
        "--log-level", "info"
    )

    Start-Sleep -Seconds 2
}

Write-Host "=== 全部启动完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "Nginx upstream 应配置:"
for ($i = 0; $i -lt $Workers; $i++) {
    $Port = $BasePort + $i
    Write-Host "    server 127.0.0.1:${Port};"
}
