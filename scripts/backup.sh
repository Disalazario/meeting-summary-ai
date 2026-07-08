#!/usr/bin/env bash
# Бэкап ценных данных: backend/app.db (SQLite) и backend/uploads/.
#
# Использование:
#   ./scripts/backup.sh                  # бэкап в ./backups/
#   BACKUP_DIR=/mnt/d/backups ./scripts/backup.sh
#   BACKUP_REMOTE=user@vps:/srv/backups ./scripts/backup.sh   # + rsync на VPS
#
# Cron (ежедневно в 03:30):
#   30 3 * * * cd /webhome/summary_ai && ./scripts/backup.sh >> backend/logs/backup.log 2>&1
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="$PROJECT_DIR/backend/app.db"
UPLOADS_DIR="$PROJECT_DIR/backend/uploads"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
KEEP_DB_DUMPS="${KEEP_DB_DUMPS:-14}"

timestamp="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR/db"

echo "[$timestamp] Бэкап БД: $DB_PATH"
# Online-бэкап: безопасен при работающем backend (в отличие от cp)
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/db/app-$timestamp.db'"
gzip "$BACKUP_DIR/db/app-$timestamp.db"
echo "  -> $BACKUP_DIR/db/app-$timestamp.db.gz ($(du -h "$BACKUP_DIR/db/app-$timestamp.db.gz" | cut -f1))"

# Ротация: оставляем последние N дампов
ls -1t "$BACKUP_DIR/db"/app-*.db.gz 2>/dev/null | tail -n +$((KEEP_DB_DUMPS + 1)) | xargs -r rm -f

# Uploads: инкрементальное зеркало (rsync копирует только новое)
if [ -d "$UPLOADS_DIR" ]; then
    echo "[$timestamp] Зеркало uploads -> $BACKUP_DIR/uploads/"
    rsync -a --delete "$UPLOADS_DIR/" "$BACKUP_DIR/uploads/"
fi

# Опционально: выгрузка на удалённый хост (VPS / внешний диск)
if [ -n "$BACKUP_REMOTE" ]; then
    echo "[$timestamp] rsync на $BACKUP_REMOTE"
    rsync -az "$BACKUP_DIR/db/" "$BACKUP_REMOTE/db/"
    rsync -az --delete "$BACKUP_DIR/uploads/" "$BACKUP_REMOTE/uploads/"
fi

echo "[$timestamp] Бэкап завершён."
