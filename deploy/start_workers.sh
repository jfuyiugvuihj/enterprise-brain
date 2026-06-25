#!/bin/bash
# ============================================================
# 企业智脑 — 启动多个 uvicorn 实例 (Layer 4)
# 用法: bash deploy/start_workers.sh [实例数] [起始端口]
# ============================================================

WORKERS=${1:-3}
BASE_PORT=${2:-8001}
APP="app.main:app"

echo "=== 企业智脑 — 启动 ${WORKERS} 个 uvicorn 实例 ==="

# 停掉旧进程
pkill -f "uvicorn ${APP}" 2>/dev/null
sleep 1

for ((i=0; i<WORKERS; i++)); do
    PORT=$((BASE_PORT + i))
    LOGFILE="logs/uvicorn_${PORT}.log"
    mkdir -p logs

    echo "  启动实例 #$((i+1)) 端口 ${PORT} ..."
    nohup python -m uvicorn ${APP} \
        --host 0.0.0.0 \
        --port ${PORT} \
        --loop none \
        --log-level info \
        > "${LOGFILE}" 2>&1 &

    sleep 1
done

echo "=== 全部启动完成 ==="
echo ""
echo "实例列表:"
for ((i=0; i<WORKERS; i++)); do
    PORT=$((BASE_PORT + i))
    echo "  http://0.0.0.0:${PORT}"
done
echo ""
echo "Nginx 上游配置:"
echo "  upstream enterprise_brain {"
for ((i=0; i<WORKERS; i++)); do
    PORT=$((BASE_PORT + i))
    echo "      server 127.0.0.1:${PORT};"
done
echo "  }"
