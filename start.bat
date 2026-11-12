@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python не найден. Установите его с https://www.python.org/downloads/
  echo При установке поставьте галочку "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist .venv (
  echo Первый запуск: устанавливаю нужные компоненты, подождите...
  python -m venv .venv
  .venv\Scripts\python -m pip install -q -r requirements.txt
)

if not exist .env (
  echo.
  set /p TOKEN=Вставьте токен бота от @BotFather и нажмите Enter: 
  call echo BOT_TOKEN=%%TOKEN%%> .env
)

echo.
echo Бот запущен. Не закрывайте это окно, пока бот нужен.
.venv\Scripts\python -m rzn_bot
pause
