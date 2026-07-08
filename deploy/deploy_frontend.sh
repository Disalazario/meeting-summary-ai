#!/usr/bin/env bash
# Сборка фронта + заливка на VPS.
#
# Запускать с ПК из любого места — скрипт сам перейдёт в frontend/.

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# Параметры — заполните
# ──────────────────────────────────────────────────────────────────────
VPS_HOST="${VPS_HOST:-root@<VPS_IP>}"
WEB_ROOT="/var/www/meet"

if [[ "$VPS_HOST" == *"<VPS_IP>"* ]]; then
    echo "ERROR: впишите VPS_HOST в начало скрипта (или экспортируйте env)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"

cd "$FRONTEND_DIR"

if [[ ! -f .env.production ]]; then
    echo "ERROR: $FRONTEND_DIR/.env.production не найден."
    echo "       Скопируйте .env.production.example и впишите VITE_API_URL."
    exit 1
fi

echo "==> npm run build (основной фронт с .env.production)..."
npm run build

# --exclude=miniapp/ КРИТИЧНО: иначе --delete сносит каталог Mini App, который
# раздаётся nginx-ом отдельно с того же /var/www/meet
echo "==> rsync $FRONTEND_DIR/dist/  →  $VPS_HOST:$WEB_ROOT/  (без miniapp/)"
rsync -avz --delete --exclude='miniapp/' --exclude='miniapp/**' dist/ "$VPS_HOST:$WEB_ROOT/"

echo
echo "==> Сборка Mini App..."
MINIAPP_DIR="$FRONTEND_DIR/miniapp"
if [[ -f "$MINIAPP_DIR/package.json" ]]; then
    cd "$MINIAPP_DIR"
    if [[ ! -f .env.production ]]; then
        # Same-origin: пустой VITE_API_URL → mini app ходит на /api/miniapp того же домена
        echo "VITE_API_URL=" > .env.production
        chmod 600 .env.production
    fi
    npm run build
    echo "==> rsync $MINIAPP_DIR/dist/  →  $VPS_HOST:$WEB_ROOT/miniapp/"
    rsync -avz --delete dist/ "$VPS_HOST:$WEB_ROOT/miniapp/"
fi

echo "✅ Фронт и Mini App обновлены."
