#!/usr/bin/env bash
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Установите Python 3: https://www.python.org/downloads/"; exit 1; }
if [ ! -d .venv ]; then
  echo "Первый запуск: устанавливаю нужные компоненты, подождите..."
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt || exit 1
fi
if [ ! -f .env ]; then
  read -rp "Вставьте токен бота от @BotFather и нажмите Enter: " TOKEN
  echo "BOT_TOKEN=$TOKEN" > .env
fi
echo "Бот запущен. Не закрывайте это окно, пока бот нужен."
exec .venv/bin/python -m rzn_bot
