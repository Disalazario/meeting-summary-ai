#!/usr/bin/env bash
# Первоначальная настройка VPS под Meeting Summary AI.
#
# Запускать на VPS под root (или sudo bash setup_vps.sh).
# Перед запуском заполните DOMAIN и EMAIL ниже.

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# Параметры — заполните перед запуском
# ──────────────────────────────────────────────────────────────────────
DOMAIN="${DOMAIN:-meet.example.ru}"        # ваш домен
EMAIL="${EMAIL:-admin@example.ru}"         # email для Let's Encrypt
WEB_ROOT="/var/www/meet"

# Где скрипт лежит (чтобы найти соседний nginx.conf)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$DOMAIN" == "meet.example.ru" ]]; then
    echo "ERROR: впишите свой DOMAIN в начало скрипта"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────
# 1. Пакеты
# ──────────────────────────────────────────────────────────────────────
echo "==> Установка nginx, certbot, ufw, rsync..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    nginx certbot python3-certbot-nginx ufw rsync

# ──────────────────────────────────────────────────────────────────────
# 2. Firewall
# ──────────────────────────────────────────────────────────────────────
echo "==> Настройка ufw..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ──────────────────────────────────────────────────────────────────────
# 3. Каталоги
# ──────────────────────────────────────────────────────────────────────
echo "==> Создание каталогов..."
mkdir -p "$WEB_ROOT"
mkdir -p /var/www/certbot
# заглушка чтобы nginx не падал до выпуска сертификата
cat > "$WEB_ROOT/index.html" <<EOF
<!doctype html><meta charset="utf-8"><title>Meeting Summary AI</title>
<h1>Скоро здесь будет фронт.</h1>
EOF

# ──────────────────────────────────────────────────────────────────────
# 4. nginx-конфиг
# ──────────────────────────────────────────────────────────────────────
echo "==> Установка nginx-конфига для $DOMAIN..."
sed "s|__DOMAIN__|$DOMAIN|g" "$SCRIPT_DIR/nginx.conf" \
    > /etc/nginx/sites-available/meet
ln -sf /etc/nginx/sites-available/meet /etc/nginx/sites-enabled/meet
# отключить дефолтный, если включён
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl reload nginx

# ──────────────────────────────────────────────────────────────────────
# 5. Let's Encrypt
# ──────────────────────────────────────────────────────────────────────
echo "==> Выпуск сертификата Let's Encrypt для $DOMAIN..."
certbot --nginx -d "$DOMAIN" \
    --non-interactive --agree-tos -m "$EMAIL" --redirect

systemctl reload nginx

# ──────────────────────────────────────────────────────────────────────
# 6. Итог
# ──────────────────────────────────────────────────────────────────────
echo
echo "✅ VPS готов."
echo "   Открыть в браузере:  https://$DOMAIN"
echo "   Залить фронт:        rsync -avz dist/ root@<VPS_IP>:$WEB_ROOT/"
echo "   Поднять туннель с ПК: bash deploy/tunnel.sh"
