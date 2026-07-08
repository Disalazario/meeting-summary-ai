# Деплой: VPS в РФ + reverse SSH-туннель на домашний ПК

Цель — поднять публичный домен с HTTPS, который раздаёт фронт со стороны VPS,
а API проксирует на uvicorn, который продолжает крутиться на вашем ПК.
Цена — порядка 200–300 ₽/мес за VPS. Всё внутри РФ, ничего не блокируется.

```
[user@browser]
       │ https://meet.example.ru
       ▼
[VPS в РФ] nginx
   ├── /        → /var/www/meet (vite build)
   └── /api/    → 127.0.0.1:18000  (обратный SSH-туннель)
                          │
                          ▼
                  [ваш ПК] uvicorn :8000
```

---

## Что вам нужно перед стартом

1. **Купленный VPS** в РФ. Минимум: 1 vCPU / 1 ГБ RAM / 10 ГБ SSD, Ubuntu 22.04.
   Дешёвые провайдеры: Timeweb Cloud, RuVDS, Beget, Selectel.
2. **Домен или поддомен**, направленный A-записью на IP VPS. Можно временно
   использовать предоставляемый VPS-провайдером поддомен (`*.tw1.su`,
   `*.beget.tech` и т.п.) — HTTPS на нём тоже работает.
3. **SSH-доступ** на VPS как root (или пользователь с sudo).
4. На **ПК** — `ssh`, `autossh`, `rsync`, `npm`. В WSL ставится так:
   ```bash
   sudo apt install -y autossh rsync
   ```

---

## Шаг 1. Начальная настройка VPS

Подставьте свои значения в начало скрипта `deploy/setup_vps.sh`:

- `DOMAIN` — ваш домен (например, `meet.example.ru`)
- `EMAIL` — email для Let's Encrypt

Затем:

```bash
# с ПК
scp deploy/setup_vps.sh root@<VPS_IP>:/root/
ssh root@<VPS_IP> "bash /root/setup_vps.sh"
```

Скрипт:
- ставит nginx, certbot, ufw
- открывает 22/80/443
- кладёт `nginx.conf` (с подстановкой домена) в `/etc/nginx/sites-enabled/meet`
- выпускает Let's Encrypt сертификат
- создаёт каталог `/var/www/meet` для статики

---

## Шаг 2. Поднять обратный SSH-туннель с ПК

На **ПК** (WSL) разово настройте ключи:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/meet_tunnel        # если ключа ещё нет
ssh-copy-id -i ~/.ssh/meet_tunnel.pub root@<VPS_IP>
```

Запустить туннель:

```bash
# подставьте <VPS_IP> в deploy/tunnel.sh
bash deploy/tunnel.sh
```

После этого на VPS порт `127.0.0.1:18000` проксирует на ваш `localhost:8000`.

Чтобы туннель пережил перезапуск WSL — добавьте в WSL `systemd` сервис
(шаблон в `deploy/tunnel.service`, см. комментарии внутри).

---

## Шаг 3. Настроить backend на продовый домен

Отредактируйте `/webhome/summary_ai/.env`:

```
CORS_ORIGINS=https://meet.example.ru
APP_URL=https://meet.example.ru
```

Перезапустить backend:
```bash
./start.sh stop && ./start.sh backend
```

---

## Шаг 4. Собрать и залить фронт

```bash
# на ПК
cd /webhome/summary_ai/frontend

# .env.production.example уже лежит — скопируйте и впишите домен
cp .env.production.example .env.production
# отредактируйте VITE_API_URL=https://meet.example.ru

# подставьте свой VPS в начало скрипта
bash ../deploy/deploy_frontend.sh
```

Скрипт делает `npm run build` и `rsync dist/ → VPS:/var/www/meet/`.

---

## Шаг 5. Проверить

```
curl https://meet.example.ru/api/health
# {"status":"ok","version":"2.0.0"}
```

Открыть `https://meet.example.ru` в браузере — должна загрузиться LoginPage.
Войти, попробовать загрузить аудио. Если работает — готово.

---

## Что важно помнить

- **Туннель должен быть запущен** на ПК всё время, пока пользуется демо.
  Выключили WSL → демо лежит. Это нормально для временного решения.
- **Аудио идёт через ваш домашний канал**: upload-скорость дома = скорость
  загрузки больших файлов. На WAV/mp3 по 10–30 МБ нормально, на видео в гигабайт
  будет тормозить.
- **VPS защищается**: ufw настроен на 22/80/443. Сам uvicorn НЕ слушает
  публично — туннель приходит на `127.0.0.1`, никто извне его не дёрнет.
- **Сертификат Let's Encrypt продлевается автоматически** (cron от certbot).
  Раз в год можно убедиться, что `certbot renew --dry-run` проходит.
- **Бэкапы**: на ПК `backend/app.db` и `backend/uploads/` — это всё ценное.
  Готовый скрипт: `./scripts/backup.sh` (online-бэкап SQLite + rsync-зеркало uploads,
  ротация 14 дампов). Назначение настраивается через `BACKUP_DIR` (внешний диск)
  и `BACKUP_REMOTE` (rsync на VPS). Добавить в cron:
  ```bash
  30 3 * * * cd /webhome/summary_ai && ./scripts/backup.sh >> backend/logs/backup.log 2>&1
  ```
