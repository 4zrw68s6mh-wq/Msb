# Бот проверки ИНН в реестре Росздравнадзора

Telegram-бот: пользователь присылает ИНН, бот проверяет контрольную сумму и ищет
лицензии организации/ИП в [реестре лицензий Росздравнадзора](https://roszdravnadzor.gov.ru/services/licenses).

## Запуск

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # впишите BOT_TOKEN от @BotFather
python -m rzn_bot
```

Использование: отправьте боту `7707083893` или `/inn 7707083893`.

## Настройка запроса к сайту

У Росздравнадзора нет публичного API: бот повторяет AJAX-запрос страницы реестра.
Если сайт поменяет формат, откройте страницу реестра, DevTools → Network, выполните
поиск по ИНН и перенесите адрес и имя параметра в `.env`:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `RZN_SEARCH_URL` | `https://roszdravnadzor.gov.ru/ajax/services/licenses` | адрес запроса |
| `RZN_INN_PARAM` | `q_inn` | имя параметра с ИНН |
| `RZN_METHOD` | `POST` | `POST` или `GET` |
| `RZN_SSL_VERIFY` | `true` | `true`, `false` или путь к PEM (Russian Trusted Root CA) |
| `RZN_TIMEOUT` | `30` | таймаут, сек |

Ответ разбирается и как JSON (включая формат DataTables), и как HTML-таблица.

## Тесты

```bash
pip install pytest && python -m pytest -q
```
