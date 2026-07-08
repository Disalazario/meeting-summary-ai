#!/usr/bin/env bash
# Обратный SSH-туннель ПК → VPS.
# На VPS открывается 127.0.0.1:18000, проксирующий на ваш uvicorn 8000.
#
# Перед запуском — заполните VPS_HOST.

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# Параметры — заполните
# ──────────────────────────────────────────────────────────────────────
VPS_HOST="${VPS_HOST:-root@<VPS_IP>}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/meet_tunnel}"

# На VPS: какой порт слушаем (127.0.0.1)
REMOTE_PORT=18000
# На ПК: куда проксируем (uvicorn по умолчанию)
LOCAL_PORT=8000

if [[ "$VPS_HOST" == *"<VPS_IP>"* ]]; then
    echo "ERROR: впишите VPS_HOST в начало скрипта (или экспортируйте env)"
    exit 1
fi

if ! command -v autossh &>/dev/null; then
    echo "ERROR: autossh не установлен. sudo apt install -y autossh"
    exit 1
fi

echo "==> Reverse tunnel $VPS_HOST:$REMOTE_PORT  →  localhost:$LOCAL_PORT"

# -M 0  — отключаем monitoring-port autossh (используем ServerAliveInterval)
# -N    — не открывать shell
# -f    — в фон
exec autossh -M 0 -N -f \
    -i "$SSH_KEY" \
    -o "ExitOnForwardFailure=yes" \
    -o "ServerAliveInterval=30" \
    -o "ServerAliveCountMax=3" \
    -o "StrictHostKeyChecking=accept-new" \
    -R "127.0.0.1:${REMOTE_PORT}:127.0.0.1:${LOCAL_PORT}" \
    "$VPS_HOST"
