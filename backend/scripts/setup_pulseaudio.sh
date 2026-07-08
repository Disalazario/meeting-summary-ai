#!/bin/bash
set -e
echo "=== Настройка PulseAudio для захвата аудио бота ==="

sudo apt update
sudo apt install -y pulseaudio pulseaudio-utils

# Конфигурация: виртуальный sink для перехвата аудио
mkdir -p ~/.config/pulse
cat > ~/.config/pulse/default.pa << 'EOF'
.include /etc/pulse/default.pa

# Virtual sink — сюда Chromium будет выводить аудио
load-module module-null-sink sink_name=bot_capture sink_properties=device.description=Bot_Audio_Capture

# Monitor source — отсюда ffmpeg будет записывать
load-module module-virtual-source source_name=bot_monitor master=bot_capture.monitor
EOF

# WSL2: удалить сломанные симлинки от WSLg
rm -f /run/user/$(id -u)/pulse/pid /run/user/$(id -u)/pulse/native 2>/dev/null

# Убираем WSLg PulseAudio переменную (если есть)
unset PULSE_SERVER

# Запуск
pulseaudio --kill 2>/dev/null || true
sleep 1
pulseaudio --start --daemonize=true --exit-idle-time=-1

# Проверка
echo "=== Проверка ==="
pactl list short sinks | grep bot_capture && echo "bot_capture sink создан" || echo "Ошибка"

echo ""
echo "Готово!"
echo ""
echo "ВАЖНО: перед запуском бэкенда выполните:"
echo "  unset PULSE_SERVER"
echo ""
echo "Для тестовой записи:"
echo "  unset PULSE_SERVER && ffmpeg -f pulse -i bot_capture.monitor -t 5 test_capture.wav"
