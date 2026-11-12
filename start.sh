#!/usr/bin/env bash
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Установите Python 3: https://www.python.org/downloads/"; exit 1; }

deps_ok() { [ -x .venv/bin/python ] && .venv/bin/python -c "import aiogram, httpx, bs4, dotenv" 2>/dev/null; }

if ! deps_ok; then
  echo "Устанавливаю нужные компоненты, подождите 1-2 минуты..."
  rm -rf .venv
  python3 -m venv .venv \
    && .venv/bin/python -m pip install --upgrade pip >/dev/null \
    && .venv/bin/python -m pip install -r requirements.txt
  if ! deps_ok; then
    echo
    echo "Не получилось установить компоненты. Сделайте скриншот этого окна и пришлите его."
    exit 1
  fi
fi

if [ ! -f .env ]; then
  read -rp "Вставьте токен бота от @BotFather и нажмите Enter: " TOKEN
  echo "BOT_TOKEN=$TOKEN" > .env
fi
echo "Бот запущен. Не закрывайте это окно, пока бот нужен."
exec .venv/bin/python -m rzn_bot
