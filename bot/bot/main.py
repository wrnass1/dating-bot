import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from bot.api_client import ApiClient
from bot.settings import settings


logger = logging.getLogger("bot")


def _format_welcome(is_new: bool) -> str:
    if is_new:
        return (
            "Привет! Я тебя зарегистрировал.\n\n"
            "Дальше будет создание анкеты и лента."
        )
    return "С возвращением! Ты уже зарегистрирован(а)."


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    api = ApiClient(settings.api_base_url)

    @dp.message(Command("start"))
    async def start(message: Message) -> None:
        tg = message.from_user
        if tg is None:
            await message.answer("Не смог прочитать данные пользователя Telegram.")
            return

        try:
            result = await api.upsert_telegram_user(
                telegram_id=tg.id,
                username=tg.username,
                first_name=tg.first_name,
                language=tg.language_code,
            )
        except Exception:
            logger.exception("Failed to upsert telegram user")
            await message.answer("Ошибка регистрации. Попробуй ещё раз позже.")
            return

        await message.answer(_format_welcome(bool(result.get("is_new"))))

    @dp.message(Command("help"))
    async def help_cmd(message: Message) -> None:
        await message.answer("Команды:\n/start — регистрация\n/help — помощь")

    @dp.message(F.text == "/ping")
    async def ping(message: Message) -> None:
        await message.answer("pong")

    try:
        await dp.start_polling(bot)
    finally:
        await api.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

