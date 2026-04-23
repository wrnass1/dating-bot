import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.api_client import ApiClient
from bot.settings import settings


logger = logging.getLogger("bot")


class ProfileWizard(StatesGroup):
    age = State()
    gender = State()
    city = State()
    interests = State()
    about = State()
    pref_gender = State()
    pref_age_min = State()
    pref_age_max = State()
    pref_city = State()


def _format_welcome(is_new: bool) -> str:
    if is_new:
        return (
            "Привет! Я тебя зарегистрировал.\n\n"
            "Команды:\n"
            "/profile — создать/обновить анкету\n"
            "/me — показать мою анкету\n"
            "/feed — лента анкет"
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
        await message.answer(
            "Команды:\n"
            "/start — регистрация\n"
            "/profile — создать/обновить анкету\n"
            "/me — показать мою анкету\n"
            "/feed — лента анкет\n"
            "/help — помощь"
        )

    @dp.message(F.text == "/ping")
    async def ping(message: Message) -> None:
        await message.answer("pong")

    @dp.message(Command("me"))
    async def me(message: Message) -> None:
        tg = message.from_user
        if tg is None:
            return
        try:
            prof = await api.get_profile(telegram_id=tg.id)
        except Exception:
            await message.answer("Анкета не найдена. Используй /profile чтобы создать.")
            return

        text = (
            f"Твоя анкета:\n"
            f"- Возраст: {prof.get('age')}\n"
            f"- Пол: {prof.get('gender')}\n"
            f"- Город: {prof.get('city')}\n"
            f"- Интересы: {prof.get('interests')}\n"
            f"- О себе: {prof.get('about')}\n\n"
            f"Предпочтения:\n"
            f"- Пол: {prof.get('pref_gender')}\n"
            f"- Возраст: {prof.get('pref_age_min')}–{prof.get('pref_age_max')}\n"
            f"- Город: {prof.get('pref_city')}\n"
        )
        await message.answer(text)

    @dp.message(Command("profile"))
    async def profile_start(message: Message, state: FSMContext) -> None:
        tg = message.from_user
        if tg is None:
            return
        await state.clear()
        await state.update_data(telegram_id=tg.id)
        await state.set_state(ProfileWizard.age)
        await message.answer("Создаём/обновляем анкету. Сколько тебе лет? (18–120)")

    @dp.message(ProfileWizard.age)
    async def profile_age(message: Message, state: FSMContext) -> None:
        try:
            age = int((message.text or "").strip())
        except Exception:
            await message.answer("Введи число, например 27.")
            return
        if age < 18 or age > 120:
            await message.answer("Возраст должен быть 18–120.")
            return
        await state.update_data(age=age)
        await state.set_state(ProfileWizard.gender)
        await message.answer("Пол? (male/female/other)")

    @dp.message(ProfileWizard.gender)
    async def profile_gender(message: Message, state: FSMContext) -> None:
        gender = (message.text or "").strip().lower()
        if gender not in ("male", "female", "other"):
            await message.answer("Варианты: male / female / other")
            return
        await state.update_data(gender=gender)
        await state.set_state(ProfileWizard.city)
        await message.answer("Город? (например: Москва)")

    @dp.message(ProfileWizard.city)
    async def profile_city(message: Message, state: FSMContext) -> None:
        city = (message.text or "").strip()
        if not city:
            await message.answer("Введи город текстом.")
            return
        await state.update_data(city=city)
        await state.set_state(ProfileWizard.interests)
        await message.answer("Интересы? (через запятую)")

    @dp.message(ProfileWizard.interests)
    async def profile_interests(message: Message, state: FSMContext) -> None:
        interests = (message.text or "").strip()
        await state.update_data(interests=interests)
        await state.set_state(ProfileWizard.about)
        await message.answer("Коротко о себе (1-2 предложения).")

    @dp.message(ProfileWizard.about)
    async def profile_about(message: Message, state: FSMContext) -> None:
        about = (message.text or "").strip()
        await state.update_data(about=about)
        await state.set_state(ProfileWizard.pref_gender)
        await message.answer("Кого ищешь по полу? (male/female/other)")

    @dp.message(ProfileWizard.pref_gender)
    async def profile_pref_gender(message: Message, state: FSMContext) -> None:
        gender = (message.text or "").strip().lower()
        if gender not in ("male", "female", "other"):
            await message.answer("Варианты: male / female / other")
            return
        await state.update_data(pref_gender=gender)
        await state.set_state(ProfileWizard.pref_age_min)
        await message.answer("Мин возраст партнёра? (18–120)")

    @dp.message(ProfileWizard.pref_age_min)
    async def profile_pref_age_min(message: Message, state: FSMContext) -> None:
        try:
            val = int((message.text or "").strip())
        except Exception:
            await message.answer("Введи число.")
            return
        if val < 18 or val > 120:
            await message.answer("Возраст должен быть 18–120.")
            return
        await state.update_data(pref_age_min=val)
        await state.set_state(ProfileWizard.pref_age_max)
        await message.answer("Макс возраст партнёра? (18–120)")

    @dp.message(ProfileWizard.pref_age_max)
    async def profile_pref_age_max(message: Message, state: FSMContext) -> None:
        try:
            val = int((message.text or "").strip())
        except Exception:
            await message.answer("Введи число.")
            return
        if val < 18 or val > 120:
            await message.answer("Возраст должен быть 18–120.")
            return
        data = await state.get_data()
        if "pref_age_min" in data and val < int(data["pref_age_min"]):
            await message.answer("Максимальный возраст должен быть >= минимального.")
            return
        await state.update_data(pref_age_max=val)
        await state.set_state(ProfileWizard.pref_city)
        await message.answer("Город партнёра? (можно такой же, как твой)")

    @dp.message(ProfileWizard.pref_city)
    async def profile_pref_city(message: Message, state: FSMContext) -> None:
        pref_city = (message.text or "").strip()
        if not pref_city:
            await message.answer("Введи город текстом.")
            return
        data = await state.get_data()
        telegram_id = int(data["telegram_id"])
        fields = {k: v for k, v in data.items() if k != "telegram_id"}
        fields["pref_city"] = pref_city

        try:
            await api.upsert_profile(telegram_id=telegram_id, **fields)
        except Exception:
            logger.exception("Failed to upsert profile")
            await message.answer("Не получилось сохранить анкету. Попробуй позже.")
            return
        finally:
            await state.clear()

        await message.answer("Анкета сохранена! Теперь можно открыть /feed.")

    def _feed_kb(profile_id: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="👍 Like", callback_data=f"like:{profile_id}"),
                    InlineKeyboardButton(text="➡️ Skip", callback_data=f"skip:{profile_id}"),
                ]
            ]
        )

    def _format_feed_card(card: dict) -> str:
        return (
            f"Анкета:\n"
            f"- Возраст: {card.get('age')}\n"
            f"- Пол: {card.get('gender')}\n"
            f"- Город: {card.get('city')}\n"
            f"- Интересы: {card.get('interests')}\n"
            f"- О себе: {card.get('about')}\n"
            f"\nScore: {card.get('combined_score'):.1f}"
        )

    async def _send_next_feed(message: Message, api: ApiClient) -> None:
        tg = message.from_user
        if tg is None:
            return
        try:
            card = await api.feed_next(telegram_id=tg.id)
        except Exception:
            await message.answer("Лента пуста или анкета не создана. Сначала сделай /profile.")
            return
        await message.answer(_format_feed_card(card), reply_markup=_feed_kb(card["profile_id"]))

    @dp.message(Command("feed"))
    async def feed(message: Message) -> None:
        await _send_next_feed(message, api)

    @dp.callback_query(F.data.startswith("like:") | F.data.startswith("skip:"))
    async def on_feed_action(call: CallbackQuery) -> None:
        tg = call.from_user
        if tg is None:
            return
        data = call.data or ""
        action, profile_id = data.split(":", 1)
        try:
            res = await api.interact(telegram_id=tg.id, to_profile_id=profile_id, action=action)
        except Exception:
            logger.exception("Failed to send interaction")
            await call.answer("Ошибка. Попробуй ещё раз.")
            return

        if res.get("is_match"):
            await call.answer("Мэтч!")
            await call.message.answer("У вас мэтч! Можешь написать человеку в Telegram, если знаешь его контакт.")
        else:
            await call.answer("Ок")

        if call.message:
            await _send_next_feed(call.message, api)

    try:
        await dp.start_polling(bot)
    finally:
        await api.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

