"""Telegram-бот: проверка ИНН в реестре лицензий Росздравнадзора."""
from __future__ import annotations

import asyncio
import html
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

from .client import PAGE_URL, RznClient, RznError, SearchResult
from .inn import normalize_inn, validate_inn

MAX_RECORDS = 10
MAX_MESSAGE = 4000

log = logging.getLogger("rzn_bot")


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


def build_dispatcher(client: RznClient) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    @dp.message(Command("help"))
    async def start(message: Message) -> None:
        await message.answer(
            "Отправьте ИНН организации (10 цифр) или ИП (12 цифр) — я проверю наличие "
            "лицензий в реестре Росздравнадзора.\n\nМожно также: <code>/inn 7707083893</code>"
        )

    @dp.message(Command("inn"))
    @dp.message(F.text)
    async def check(message: Message) -> None:
        text = message.text or ""
        if text.startswith("/inn"):
            text = text[4:]
        inn = normalize_inn(text)
        ok, error = validate_inn(inn)
        if not ok:
            await message.answer(f"⚠️ {error}")
            return
        await message.bot.send_chat_action(message.chat.id, "typing")
        try:
            result = await client.search_by_inn(inn)
        except RznError as exc:
            log.warning("Ошибка запроса для %s: %s", inn, exc)
            await message.answer(f"❌ {html.escape(str(exc))}\nПопробуйте позже.")
            return
        except Exception:
            log.exception("Непредвиденная ошибка для %s", inn)
            await message.answer("❌ Не удалось разобрать ответ сайта. Попробуйте позже.")
            return
        for chunk in format_result(result):
            await message.answer(chunk, disable_web_page_preview=True)

    return dp


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Не задан BOT_TOKEN (см. .env.example)")
    client = RznClient(
        search_url=os.getenv("RZN_SEARCH_URL", "https://roszdravnadzor.gov.ru/ajax/services/licenses"),
        inn_param=os.getenv("RZN_INN_PARAM", "q_inn"),
        method=os.getenv("RZN_METHOD", "POST"),
        verify=_ssl_verify(os.getenv("RZN_SSL_VERIFY", "true")),
        timeout=float(os.getenv("RZN_TIMEOUT", "30")),
    )
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await build_dispatcher(client).start_polling(bot)
    finally:
        await client.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
