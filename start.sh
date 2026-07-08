#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Meeting Summary AI — Единый скрипт запуска
# ═══════════════════════════════════════════════════════════════════
#
# Использование:
#   ./start.sh          — запуск backend + frontend
#   ./start.sh backend  — только backend
#   ./start.sh frontend — только frontend
#   ./start.sh stop     — остановить все процессы
#
# ═══════════════════════════════════════════════════════════════════

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="/home/user/.virtualenvs/tg_doc_bot"
PID_DIR="$PROJECT_DIR/.pids"
LOG_DIR="$BACKEND_DIR/logs"

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

mkdir -p "$PID_DIR" "$LOG_DIR"

# ── Функции ──────────────────────────────────────────────────────

check_deps() {
    local missing=()

    command -v ffmpeg &>/dev/null || missing+=("ffmpeg")
    command -v pactl &>/dev/null  || missing+=("pulseaudio-utils")
    command -v node &>/dev/null   || missing+=("nodejs")
    command -v npm &>/dev/null    || missing+=("npm")

    if [ ! -d "$VENV_DIR" ]; then
        missing+=("python venv ($VENV_DIR)")
    fi

    if [ ! -f "$PROJECT_DIR/.env" ]; then
        missing+=(".env файл (скопируйте .env.example)")
    fi

    if [ ${#missing[@]} -ne 0 ]; then
        echo -e "${RED}Не найдены зависимости:${NC}"
        for dep in "${missing[@]}"; do
            echo -e "  ${RED}✗${NC} $dep"
        done
        echo ""
        echo "Запустите: bash scripts/setup_env.sh"
        exit 1
    fi
}

setup_pulseaudio() {
    echo -e "${BLUE}[PulseAudio]${NC} Настройка виртуального sink..."

    export PULSE_SERVER="unix:/mnt/wslg/PulseServer"

    # Проверить что PulseAudio доступен
    if ! pactl info &>/dev/null; then
        echo -e "${YELLOW}[PulseAudio]${NC} PulseAudio не доступен, пропускаем"
        return
    fi

    # Создать bot_capture sink если не существует
    if ! pactl list short sinks 2>/dev/null | grep -q "bot_capture"; then
        pactl load-module module-null-sink \
            sink_name=bot_capture \
            sink_properties=device.description=Bot_Audio_Capture \
            &>/dev/null || true
        echo -e "${GREEN}[PulseAudio]${NC} Sink 'bot_capture' создан"
    else
        echo -e "${GREEN}[PulseAudio]${NC} Sink 'bot_capture' уже существует"
    fi

    # Установить как default
    pactl set-default-sink bot_capture &>/dev/null || true
    echo -e "${GREEN}[PulseAudio]${NC} Default sink → bot_capture"
}

start_ollama() {
    echo -e "${BLUE}[Ollama]${NC} Проверка LLM сервиса..."

    # Проверить что ollama установлен
    if ! command -v ollama &>/dev/null; then
        echo -e "${YELLOW}[Ollama]${NC} Не установлен, пропускаем"
        echo -e "${YELLOW}[Ollama]${NC} Для установки: curl -fsSL https://ollama.com/install.sh | sh"
        return
    fi

    # Проверить запущен ли
    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        echo -e "${GREEN}[Ollama]${NC} Уже запущен"
        return
    fi

    # Запустить в фоне
    echo -e "${BLUE}[Ollama]${NC} Запуск сервиса..."
    nohup ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
    echo $! > "$PID_DIR/ollama.pid"

    # Ждём пока станет доступен (макс 10 секунд)
    for i in $(seq 1 10); do
        if curl -s http://localhost:11434/api/tags &>/dev/null; then
            echo -e "${GREEN}[Ollama]${NC} Запущен (PID: $(cat "$PID_DIR/ollama.pid"))"
            return
        fi
        sleep 1
    done

    echo -e "${YELLOW}[Ollama]${NC} Запущен, но API ещё не отвечает"
}

start_backend() {
    if [ -f "$PID_DIR/backend.pid" ] && kill -0 "$(cat "$PID_DIR/backend.pid")" 2>/dev/null; then
        echo -e "${YELLOW}[Backend]${NC} Уже запущен (PID: $(cat "$PID_DIR/backend.pid"))"
        return
    fi

    echo -e "${BLUE}[Backend]${NC} Запуск uvicorn..."

    cd "$BACKEND_DIR"
    source "$VENV_DIR/bin/activate"

    # Загрузить .env
    set -a
    source "$PROJECT_DIR/.env"
    set +a

    nohup "$VENV_DIR/bin/uvicorn" app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --reload \
        > "$LOG_DIR/uvicorn.log" 2>&1 &

    echo $! > "$PID_DIR/backend.pid"
    echo -e "${GREEN}[Backend]${NC} Запущен (PID: $!, порт: 8000)"
    echo -e "${GREEN}[Backend]${NC} Логи: $LOG_DIR/app.log"
}

start_frontend() {
    if [ -f "$PID_DIR/frontend.pid" ] && kill -0 "$(cat "$PID_DIR/frontend.pid")" 2>/dev/null; then
        echo -e "${YELLOW}[Frontend]${NC} Уже запущен (PID: $(cat "$PID_DIR/frontend.pid"))"
        return
    fi

    echo -e "${BLUE}[Frontend]${NC} Запуск Vite dev server..."

    cd "$FRONTEND_DIR"
    nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &

    echo $! > "$PID_DIR/frontend.pid"
    echo -e "${GREEN}[Frontend]${NC} Запущен (PID: $!, порт: 5173)"
}

stop_all() {
    echo -e "${BLUE}Остановка всех процессов...${NC}"

    for name in backend frontend ollama; do
        if [ -f "$PID_DIR/$name.pid" ]; then
            pid=$(cat "$PID_DIR/$name.pid")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                # Ждём завершения
                for i in $(seq 1 5); do
                    kill -0 "$pid" 2>/dev/null || break
                    sleep 1
                done
                # Принудительно если не завершился
                kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
                echo -e "${GREEN}[${name}]${NC} Остановлен (PID: $pid)"
            fi
            rm -f "$PID_DIR/$name.pid"
        fi
    done

    # Убить дочерние процессы
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    pkill -f "ollama serve" 2>/dev/null || true

    echo -e "${GREEN}Все процессы остановлены${NC}"
}

show_status() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Meeting Summary AI — запущен${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════${NC}"
    echo ""
    echo -e "  Frontend:  ${GREEN}http://localhost:5173${NC}"
    echo -e "  Backend:   ${GREEN}http://localhost:8000${NC}"
    echo -e "  API docs:  ${GREEN}http://localhost:8000/docs${NC}"
    echo -e "  Ollama:    ${GREEN}http://localhost:11434${NC}"
    echo ""
    echo -e "  Логи backend:  $LOG_DIR/app.log"
    echo -e "  Логи frontend: $LOG_DIR/frontend.log"
    echo -e "  Логи ollama:   $LOG_DIR/ollama.log"
    echo ""
    echo -e "  Остановка:  ${YELLOW}./start.sh stop${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════${NC}"
}

# ── Главный блок ─────────────────────────────────────────────────

case "${1:-all}" in
    all)
        echo -e "${BLUE}═══ Meeting Summary AI — Запуск ═══${NC}"
        echo ""
        check_deps
        setup_pulseaudio
        start_ollama
        start_backend
        sleep 2
        start_frontend
        show_status
        ;;
    backend)
        check_deps
        setup_pulseaudio
        start_ollama
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    stop)
        stop_all
        ;;
    status)
        for name in backend frontend ollama; do
            if [ -f "$PID_DIR/$name.pid" ] && kill -0 "$(cat "$PID_DIR/$name.pid")" 2>/dev/null; then
                echo -e "${GREEN}[${name}]${NC} работает (PID: $(cat "$PID_DIR/$name.pid"))"
            else
                echo -e "${RED}[${name}]${NC} не запущен"
            fi
        done
        ;;
    *)
        echo "Использование: ./start.sh [all|backend|frontend|stop|status]"
        exit 1
        ;;
esac
