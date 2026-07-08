#!/bin/bash
# Скрипт установки системных зависимостей

set -e

echo "=== Установка системных зависимостей ==="
sudo apt update
sudo apt install -y ffmpeg python3.10 python3.10-venv python3-pip \
    build-essential libffi-dev libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libglib2.0-0 libxml2 libxslt1.1

echo ""
echo "=== Создание виртуального окружения ==="
cd "$(dirname "$0")/.."
python3.10 -m venv .venv
source .venv/bin/activate

echo ""
echo "=== Установка Python-зависимостей ==="
cd backend
pip install -r requirements.txt

echo ""
echo "=== Установка frontend-зависимостей ==="
cd ../frontend
npm install

echo ""
echo "=== Копирование .env ==="
cd ..
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Скопирован .env.example -> .env"
    echo "Отредактируйте .env: задайте GEMINI_API_KEY, SECRET_KEY, HUGGINGFACE_TOKEN"
else
    echo ".env уже существует"
fi

echo ""
echo "=== Готово! ==="
echo "Для запуска:"
echo "  Backend: cd backend && source ../.venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo "  Frontend: cd frontend && npm run dev"
echo "  Создание админа: cd backend && source ../.venv/bin/activate && python ../scripts/create_admin.py"
