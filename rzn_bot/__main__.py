"""Telegram-бот: проверка ИНН в реестре лицензий Росздравнадзора.

Работает напрямую с Telegram Bot API через httpx (без aiogram), чтобы
устанавливаться на любой версии Python без сборки компонентов.
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
from pathlib import Path

import httpx

from .client import PAGE_URL, RznClient, RznError, SearchResult
from .inn import normalize_inn, validate_inn

MAX_RECORDS = 10
MAX_MESSAGE = 4000
HELP_TEXT = (
    "Отправьте ИНН организации (10 цифр) или ИП (12 цифр) — я проверю наличие "
    "лицензий в реестре Росздравнадзора.\n\nМожно также: <code>/inn 7707083893</code>"
)

log = logging.getLogger("rzn_bot")


def load_env(path: Path) -> None:
    """Простейшее чтение .env: строки вида KEY=VALUE."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _ssl_verify(value: str) -> bool | str:
    if value.lower() in ("false", "0", "no"):
        return False
    if value.lower() in ("true", "1", "yes", ""):
        return True
    return value  # путь к CA-сертификату


def format_result(result: SearchResult) -> list[str]:
    if not result.records:
        return [
            f"По ИНН <code>{result.inn}</code> лицензий в реестре Росздравнадзора не найдено.\n"
            f'Проверить вручную: <a href="{PAGE_URL}">реестр лицензий</a>'
        ]
    total = result.total or len(result.records)
    header = f"ИНН <code>{result.inn}</code>: найдено записей — <b>{total}</b>"
    if total > MAX_RECORDS:
        header += f" (показаны первые {MAX_RECORDS})"
    parts = [header]
    for i, rec in enumerate(result.records[:MAX_RECORDS], 1):
        lines = [f"<b>{i}.</b>"]
        for label, value in rec.fields:
            if len(value) > 600:
                value = value[:600] + "…"
            lines.append(f"<b>{html.escape(label)}:</b> {html.escape(value)}")
        parts.append("\n".join(lines))
    parts.append(f'Источник: <a href="{PAGE_URL}">roszdravnadzor.gov.ru</a>')

    messages, current = [], ""
    for part in parts:
        if current and len(current) + len(part) + 2 > MAX_MESSAGE:
            messages.append(current)
            current = ""
        current = f"{current}\n\n{part}" if current else part
    if current:
        messages.append(current)
    return messages


class TelegramError(Exception):
    pass


class Bot:
    def __init__(self, token: str, rzn: RznClient, proxy: str | None = None) -> None:
        self.rzn = rzn
        self.base = f"https://api.telegram.org/bot{token}/"
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(70.0, connect=15.0), proxy=proxy or None)

    async def api(self, method: str, **params):
        resp = await self.http.post(self.base + method, json=params)
        data = resp.json()
        if not data.get("ok"):
            raise TelegramError(f"{resp.status_code}: {data.get('description')}")
        return data["result"]

    async def send(self, chat_id: int, text: str) -> None:
        await self.api(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
        )

    async def handle_text(self, chat_id: int, text: str) -> None:
        text = text.strip()
        command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
        if command in ("/start", "/help"):
            await self.send(chat_id, HELP_TEXT)
            return
        if command == "/inn":
            text = text[len(text.split()[0]):]
        elif command:
            await self.send(chat_id, HELP_TEXT)
            return

        inn = normalize_inn(text)
        ok, error = validate_inn(inn)
        if not ok:
            await self.send(chat_id, f"⚠️ {error}")
            return
        try:
            await self.api("sendChatAction", chat_id=chat_id, action="typing")
        except Exception:
            pass
        try:
            result = await self.rzn.search_by_inn(inn)
        except RznError as exc:
            log.warning("Ошибка запроса для %s: %s", inn, exc)
            await self.send(chat_id, f"❌ {html.escape(str(exc))}\nПопробуйте позже.")
            return
        except Exception:
            log.exception("Непредвиденная ошибка для %s", inn)
            await self.send(chat_id, "❌ Не удалось разобрать ответ сайта. Попробуйте позже.")
            return
        for chunk in format_result(result):
            await self.send(chat_id, chunk)

    async def handle_update(self, update: dict) -> None:
        msg = update.get("message") or {}
        text = msg.get("text")
        chat_id = (msg.get("chat") or {}).get("id")
        if not text or chat_id is None:
            return
        log.info("Запрос из чата %s: %s", chat_id, text)
        try:
            await self.handle_text(chat_id, text)
        except Exception:
            log.exception("Не удалось обработать сообщение")

    async def run(self) -> None:
        while True:
            try:
                me = await self.api("getMe")
                await self.api("deleteWebhook")
                break
            except httpx.HTTPError:
                log.warning(
                    "Нет связи с Telegram (api.telegram.org). Если Telegram у вас работает только "
                    "через VPN или прокси — включите VPN или укажите TG_PROXY в файле .env. "
                    "Повтор через 10 секунд..."
                )
                await asyncio.sleep(10)
        log.info("Бот @%s работает. Напишите ему в Telegram.", me.get("username"))
        offset = None
        tasks: set[asyncio.Task] = set()
        while True:
            try:
                params = {"timeout": 50, "allowed_updates": ["message"]}
                if offset is not None:
                    params["offset"] = offset
                updates = await self.api("getUpdates", **params)
            except (httpx.HTTPError, TelegramError, ValueError) as exc:
                log.warning("Нет связи с Telegram (%s), повтор через 5 секунд", exc)
                await asyncio.sleep(5)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                task = asyncio.create_task(self.handle_update(update))
                tasks.add(task)
                task.add_done_callback(tasks.discard)

    async def close(self) -> None:
        await self.http.aclose()


async def main() -> None:
    load_env(Path(__file__).resolve().parent.parent / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Не задан BOT_TOKEN (удалите файл .env и запустите start.sh заново)")
    rzn = RznClient(
        search_url=os.getenv("RZN_SEARCH_URL", "https://roszdravnadzor.gov.ru/ajax/services/licenses"),
        inn_param=os.getenv("RZN_INN_PARAM", "q_inn"),
        method=os.getenv("RZN_METHOD", "POST"),
        verify=_ssl_verify(os.getenv("RZN_SSL_VERIFY", "true")),
        timeout=float(os.getenv("RZN_TIMEOUT", "30")),
    )
    bot = Bot(token, rzn, proxy=os.getenv("TG_PROXY", "").strip() or None)
    try:
        await bot.run()
    except TelegramError as exc:
        if "401" in str(exc) or "Unauthorized" in str(exc):
            raise SystemExit("Telegram не принял токен. Удалите файл .env и запустите start.sh заново.")
        raise
    finally:
        await rzn.close()
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
