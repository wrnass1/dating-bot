from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.redis import RedisStorage
import httpx
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
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
    photo = State()


def _format_welcome(*, is_new: bool, has_profile: bool) -> str:
    if has_profile:
        return (
            "С возвращением! Твоя анкета на месте — ничего заново заполнять не нужно.\n\n"
            "/me — посмотреть анкету\n"
            "/feed — лента\n"
            "/profile — изменить данные"
        )
    if is_new:
        return (
            "Привет! Я тебя зарегистрировал.\n\n"
            "Создай анкету: /profile\n"
            "Потом открой /feed"
        )
    return (
        "С возвращением! Анкета ещё не заполнена.\n\n"
        "Начни с /profile — в конце попросим фото."
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=settings.telegram_bot_token)
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)
    api = ApiClient(settings.api_base_url, settings.api_service_token)

    # If the bot was down/restarted, Telegram can have pending updates.
    # Dropping them prevents "duplicate" processing after restarts during development.
    await bot.delete_webhook(drop_pending_updates=True)

    async def safe_answer(message: Message, text: str, **kwargs) -> None:
        # Telegram API can be flaky (connection reset, transient network issues).
        # Retry a few times so users don't lose responses.
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                await message.answer(text, **kwargs)
                return
            except TelegramNetworkError as e:
                last_exc = e
                await asyncio.sleep(0.8 * (attempt + 1))
        logger.exception("Failed to send message after retries", exc_info=last_exc)

    async def safe_callback_answer(call: CallbackQuery, text: str | None = None) -> None:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                await call.answer(text)
                return
            except TelegramNetworkError as e:
                last_exc = e
                await asyncio.sleep(0.6 * (attempt + 1))
        logger.exception("Failed to answer callback after retries", exc_info=last_exc)

    async def safe_send_to_telegram_id(telegram_id: int, text: str) -> None:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                await bot.send_message(chat_id=telegram_id, text=text)
                return
            except TelegramNetworkError as e:
                last_exc = e
                await asyncio.sleep(0.8 * (attempt + 1))
            except Exception as e:
                # Most common: user never started the bot / blocked it.
                logger.info("Failed to notify user %s: %s", telegram_id, type(e).__name__)
                return
        logger.exception("Failed to notify user after retries", exc_info=last_exc)

    def _respond_kb(from_profile_id: str, from_telegram_id: int) -> InlineKeyboardMarkup:
        # Buttons for the user who received a like.
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="👍 Взаимно", callback_data=f"resp:like:{from_profile_id}:{from_telegram_id}"),
                    InlineKeyboardButton(text="👎 Продинамить", callback_data=f"resp:skip:{from_profile_id}:{from_telegram_id}"),
                ]
            ]
        )

    async def _download_bytes(url: str) -> bytes:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    def _pick_main_photo(photos: list[dict]) -> dict | None:
        if not photos:
            return None
        for p in photos:
            if p.get("is_main"):
                return p
        return photos[0]

    async def _answer_profile_with_main_photo(
        message: Message,
        text: str,
        photos: list[dict],
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        main_photo = _pick_main_photo(photos)
        if not main_photo:
            await safe_answer(message, text, reply_markup=reply_markup)
            return
        try:
            content = await api.download_profile_photo(photo_id=str(main_photo["photo_id"]))
            filename = f'{main_photo.get("photo_id") or "photo"}.jpg'
            await message.answer_photo(
                photo=BufferedInputFile(content, filename=filename),
                caption=text,
                reply_markup=reply_markup,
            )
        except Exception:
            logger.exception("Failed to send profile photo")
            await safe_answer(message, text, reply_markup=reply_markup)

    bot_commands = [
        BotCommand(command="start", description="Регистрация"),
        BotCommand(command="help", description="Помощь и список команд"),
        BotCommand(command="menu", description="Меню кнопок"),
        BotCommand(command="profile", description="Создать/обновить анкету"),
        BotCommand(command="me", description="Показать мою анкету"),
        BotCommand(command="feed", description="Лента анкет"),
        BotCommand(command="ping", description="Проверка: pong"),
    ]
    if settings.enable_dev_endpoints:
        bot_commands.append(BotCommand(command="reset", description="Сброс лайков и ленты (тест)"))
    await bot.set_my_commands(bot_commands, scope=BotCommandScopeDefault())

    def _main_menu_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📝 Анкета", callback_data="menu:profile"),
                    InlineKeyboardButton(text="👤 Моя анкета", callback_data="menu:me"),
                ],
                [
                    InlineKeyboardButton(text="📰 Лента", callback_data="menu:feed"),
                    InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
                ],
            ]
        )

    async def _show_menu(message: Message) -> None:
        await safe_answer(message, "Меню:", reply_markup=_main_menu_kb())

    @dp.message(Command("start"))
    async def start(message: Message, state: FSMContext) -> None:
        tg = message.from_user
        if tg is None:
            await safe_answer(message, "Не смог прочитать данные пользователя Telegram.")
            return

        await state.clear()

        try:
            result = await api.upsert_telegram_user(
                telegram_id=tg.id,
                username=tg.username,
                first_name=tg.first_name,
                language=tg.language_code,
            )
        except Exception:
            logger.exception("Failed to upsert telegram user")
            await safe_answer(message, "Ошибка регистрации. Попробуй ещё раз позже.")
            return

        await safe_answer(
            message,
            _format_welcome(
                is_new=bool(result.get("is_new")),
                has_profile=bool(result.get("has_profile")),
            ),
        )
        await _show_menu(message)

    @dp.message(Command("menu"))
    async def menu_cmd(message: Message) -> None:
        await _show_menu(message)

    @dp.message(Command("help"))
    async def help_cmd(message: Message) -> None:
        text = (
            "Команды:\n"
            "/start — регистрация\n"
            "/profile — создать/обновить анкету\n"
            "/me — показать мою анкету\n"
            "/feed — лента анкет\n"
            "/help — помощь\n\n"
            "Фото добавляется в конце заполнения анкеты (/profile)."
        )
        if settings.enable_dev_endpoints:
            text += (
                "\n\n/reset — сбросить лайки/скипы, мэтчи и кэш ленты "
                "(анкета остаётся). Для повторного теста сделай /reset на обоих аккаунтах."
            )
        await safe_answer(message, text)

    @dp.message(Command("reset"))
    async def reset_cmd(message: Message, state: FSMContext) -> None:
        if not settings.enable_dev_endpoints:
            await safe_answer(
                message,
                "Команда /reset отключена. В .env установи ENABLE_DEV_ENDPOINTS=true и перезапусти: "
                "docker compose up -d --build api bot",
            )
            return
        tg = message.from_user
        if tg is None:
            return
        await state.clear()
        try:
            result = await api.reset_user_state(telegram_id=tg.id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await safe_answer(
                    message,
                    "Сброс недоступен: на API тоже должен быть ENABLE_DEV_ENDPOINTS=true.",
                )
                return
            logger.exception("Failed to reset user state")
            await safe_answer(message, "Не удалось сбросить состояние. Попробуй позже.")
            return
        except Exception:
            logger.exception("Failed to reset user state")
            await safe_answer(message, "Не удалось сбросить состояние. Попробуй позже.")
            return

        deleted_i = int(result.get("deleted_interactions", 0))
        deleted_m = int(result.get("deleted_matches", 0))
        await safe_answer(
            message,
            "Готово. Сброшено:\n"
            f"- лайков/скипов: {deleted_i}\n"
            f"- мэтчей: {deleted_m}\n\n"
            "Анкета сохранена. Можно снова открыть /feed.",
        )

    @dp.message(StateFilter(None), F.photo)
    async def photo_upload(message: Message) -> None:
        tg = message.from_user
        if tg is None:
            return
        is_main = bool(message.caption and "main" in message.caption.lower())
        photo = message.photo[-1]
        try:
            downloaded = await bot.download(photo)
            if downloaded is None:
                raise RuntimeError("empty download")
            content = downloaded.getvalue()
            await api.upload_profile_photo(telegram_id=tg.id, content=content, is_main=is_main)
        except Exception:
            logger.exception("Failed to upload profile photo")
            await safe_answer(message, "Не удалось загрузить фото. Сначала создай анкету через /profile.")
            return
        await safe_answer(message, "Фото сохранено в S3/MinIO." + (" Установлено как главное." if is_main else ""))

    @dp.message(F.text == "/ping")
    async def ping(message: Message) -> None:
        await safe_answer(message, "pong")

    @dp.message(Command("me"))
    async def me(message: Message) -> None:
        tg = message.from_user
        if tg is None:
            return
        try:
            prof = await api.get_profile(telegram_id=tg.id)
        except Exception:
            await safe_answer(message, "Анкета не найдена. Используй /profile чтобы создать.")
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
        photos: list[dict] = []
        try:
            photos = await api.get_profile_photos(telegram_id=tg.id)
        except Exception:
            logger.exception("Failed to fetch profile photos")
        await _answer_profile_with_main_photo(message, text, photos)

    async def _ensure_registered(message: Message) -> int | None:
        tg = message.from_user
        if tg is None:
            return None
        try:
            await api.upsert_telegram_user(
                telegram_id=tg.id,
                username=tg.username,
                first_name=tg.first_name,
                language=tg.language_code,
            )
        except Exception:
            logger.exception("Failed to register telegram user")
            await safe_answer(message, "Не удалось зарегистрировать пользователя. Нажми /start и попробуй снова.")
            return None
        return tg.id

    @dp.message(Command("profile"))
    async def profile_start(message: Message, state: FSMContext) -> None:
        tg_id = await _ensure_registered(message)
        if tg_id is None:
            return
        await state.clear()
        await state.update_data(telegram_id=tg_id)
        await state.set_state(ProfileWizard.age)
        await safe_answer(message, "Создаём/обновляем анкету. Сколько тебе лет? (18–120)")

    @dp.message(ProfileWizard.age)
    async def profile_age(message: Message, state: FSMContext) -> None:
        try:
            age = int((message.text or "").strip())
        except Exception:
            await safe_answer(message, "Введи число, например 27.")
            return
        if age < 18 or age > 120:
            await safe_answer(message, "Возраст должен быть 18–120.")
            return
        await state.update_data(age=age)
        await state.set_state(ProfileWizard.gender)
        await safe_answer(message, "Пол? (male/female/other)")

    @dp.message(ProfileWizard.gender)
    async def profile_gender(message: Message, state: FSMContext) -> None:
        gender = (message.text or "").strip().lower()
        if gender not in ("male", "female", "other"):
            await safe_answer(message, "Варианты: male / female / other")
            return
        await state.update_data(gender=gender)
        await state.set_state(ProfileWizard.city)
        await safe_answer(message, "Город? (например: Москва)")

    @dp.message(ProfileWizard.city)
    async def profile_city(message: Message, state: FSMContext) -> None:
        city = (message.text or "").strip()
        if not city:
            await safe_answer(message, "Введи город текстом.")
            return
        await state.update_data(city=city)
        await state.set_state(ProfileWizard.interests)
        await safe_answer(message, "Интересы? (через запятую)")

    @dp.message(ProfileWizard.interests)
    async def profile_interests(message: Message, state: FSMContext) -> None:
        interests = (message.text or "").strip()
        await state.update_data(interests=interests)
        await state.set_state(ProfileWizard.about)
        await safe_answer(message, "Коротко о себе (1-2 предложения).")

    @dp.message(ProfileWizard.about)
    async def profile_about(message: Message, state: FSMContext) -> None:
        about = (message.text or "").strip()
        await state.update_data(about=about)
        await state.set_state(ProfileWizard.pref_gender)
        await safe_answer(message, "Кого ищешь по полу? (male/female/other)")

    @dp.message(ProfileWizard.pref_gender)
    async def profile_pref_gender(message: Message, state: FSMContext) -> None:
        gender = (message.text or "").strip().lower()
        if gender not in ("male", "female", "other"):
            await safe_answer(message, "Варианты: male / female / other")
            return
        await state.update_data(pref_gender=gender)
        await state.set_state(ProfileWizard.pref_age_min)
        await safe_answer(message, "Мин возраст партнёра? (18–120)")

    @dp.message(ProfileWizard.pref_age_min)
    async def profile_pref_age_min(message: Message, state: FSMContext) -> None:
        try:
            val = int((message.text or "").strip())
        except Exception:
            await safe_answer(message, "Введи число.")
            return
        if val < 18 or val > 120:
            await safe_answer(message, "Возраст должен быть 18–120.")
            return
        await state.update_data(pref_age_min=val)
        await state.set_state(ProfileWizard.pref_age_max)
        await safe_answer(message, "Макс возраст партнёра? (18–120)")

    @dp.message(ProfileWizard.pref_age_max)
    async def profile_pref_age_max(message: Message, state: FSMContext) -> None:
        try:
            val = int((message.text or "").strip())
        except Exception:
            await safe_answer(message, "Введи число.")
            return
        if val < 18 or val > 120:
            await safe_answer(message, "Возраст должен быть 18–120.")
            return
        data = await state.get_data()
        if "pref_age_min" in data and val < int(data["pref_age_min"]):
            await safe_answer(message, "Максимальный возраст должен быть >= минимального.")
            return
        await state.update_data(pref_age_max=val)
        await state.set_state(ProfileWizard.pref_city)
        await safe_answer(message, "Город партнёра? (можно такой же, как твой)")

    async def _finalize_profile(
        message: Message,
        state: FSMContext,
        *,
        photo_bytes: bytes | None = None,
    ) -> None:
        tg = message.from_user
        if tg is None:
            return
        data = await state.get_data()
        telegram_id = tg.id
        fields = {k: v for k, v in data.items() if k != "telegram_id"}

        try:
            await api.upsert_telegram_user(
                telegram_id=telegram_id,
                username=tg.username,
                first_name=tg.first_name,
                language=tg.language_code,
            )
            await api.upsert_profile(telegram_id=telegram_id, **fields)
            if photo_bytes is not None:
                await api.upload_profile_photo(telegram_id=telegram_id, content=photo_bytes, is_main=True)
        except httpx.HTTPStatusError as e:
            logger.exception("Failed to upsert profile")
            detail = ""
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                detail = e.response.text
            await safe_answer(message, f"Не получилось сохранить анкету: {detail or e.response.status_code}")
            return
        except Exception:
            logger.exception("Failed to upsert profile")
            await safe_answer(message, "Не получилось сохранить анкету. Попробуй позже.")
            return
        finally:
            await state.clear()

        suffix = " Фото добавлено." if photo_bytes is not None else ""
        await safe_answer(message, f"Анкета сохранена!{suffix} Теперь можно открыть /feed.")

    @dp.message(ProfileWizard.pref_city)
    async def profile_pref_city(message: Message, state: FSMContext) -> None:
        pref_city = (message.text or "").strip()
        if not pref_city:
            await safe_answer(message, "Введи город текстом.")
            return
        await state.update_data(pref_city=pref_city)
        await state.set_state(ProfileWizard.photo)
        await safe_answer(
            message,
            "Последний шаг: отправь своё фото (сжатое изображение в чат).\n"
            "Или напиши /skip, чтобы сохранить анкету без фото.",
        )

    @dp.message(ProfileWizard.photo, F.photo)
    async def profile_wizard_photo(message: Message, state: FSMContext) -> None:
        photo = message.photo[-1]
        try:
            downloaded = await bot.download(photo)
            if downloaded is None:
                raise RuntimeError("empty download")
            content = downloaded.getvalue()
        except Exception:
            logger.exception("Failed to download profile photo")
            await safe_answer(message, "Не удалось получить фото. Попробуй отправить ещё раз.")
            return
        await _finalize_profile(message, state, photo_bytes=content)

    @dp.message(ProfileWizard.photo, Command("skip"))
    async def profile_wizard_skip_photo(message: Message, state: FSMContext) -> None:
        await _finalize_profile(message, state, photo_bytes=None)

    def _feed_kb(profile_id: str, target_telegram_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="👍 Like", callback_data=f"like:{profile_id}:{target_telegram_id}"),
                    InlineKeyboardButton(text="➡️ Skip", callback_data=f"skip:{profile_id}:{target_telegram_id}"),
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

    def _format_feed_error(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                detail = exc.response.json().get("detail")
            except Exception:
                detail = exc.response.text

            if exc.response.status_code == 400:
                return f"Не могу показать ленту: {detail}"
            if exc.response.status_code == 404:
                if detail == "No profiles found":
                    return (
                        "Пока нет доступных анкет для показа.\n\n"
                        "Чтобы лента работала, нужна хотя бы 1 анкета другого пользователя."
                    )
                return str(detail)
            return f"Ошибка API ({exc.response.status_code}): {detail}"
        return "Ошибка. Попробуй ещё раз позже."

    async def _send_next_feed(message: Message, api: ApiClient) -> None:
        tg = message.from_user
        if tg is None:
            return
        try:
            card = await api.feed_next(telegram_id=tg.id)
        except Exception as e:
            await safe_answer(message, _format_feed_error(e))
            return
        feed_text = _format_feed_card(card)
        reply_markup = _feed_kb(card["profile_id"], int(card["telegram_id"]))
        photos: list[dict] = []
        try:
            photos = await api.get_profile_photos(telegram_id=int(card["telegram_id"]))
        except Exception:
            logger.exception("Failed to fetch photos for feed card")

        await _answer_profile_with_main_photo(message, feed_text, photos, reply_markup=reply_markup)

    @dp.message(Command("feed"))
    async def feed(message: Message) -> None:
        await _send_next_feed(message, api)

    @dp.callback_query(F.data.startswith("like:") | F.data.startswith("skip:"))
    async def on_feed_action(call: CallbackQuery) -> None:
        tg = call.from_user
        if tg is None:
            return
        data = call.data or ""
        parts = data.split(":")
        if len(parts) < 3:
            await safe_callback_answer(call, "Кнопка устарела. Нажми /feed ещё раз.")
            return
        action, profile_id, target_tg_id_raw = parts[0], parts[1], parts[2]
        try:
            target_tg_id = int(target_tg_id_raw)
        except Exception:
            target_tg_id = 0
        try:
            res = await api.feed_action(telegram_id=tg.id, to_profile_id=profile_id, action=action)
        except Exception:
            logger.exception("Failed to send interaction")
            await safe_callback_answer(call, "Ошибка. Попробуй ещё раз.")
            return

        if action == "like":
            await safe_callback_answer(call, "Лайк отправлен")
            if target_tg_id:
                # We need viewer's profile_id so the other user can react.
                viewer_profile_id = ""
                try:
                    viewer_prof = await api.get_profile(telegram_id=tg.id)
                    viewer_profile_id = str(viewer_prof.get("profile_id") or "")
                except Exception:
                    viewer_profile_id = ""

                await safe_send_to_telegram_id(
                    target_tg_id,
                    "Кто-то поставил лайк вашей анкете. Хотите ответить взаимностью?",
                )
                if viewer_profile_id:
                    try:
                        await bot.send_message(
                            chat_id=target_tg_id,
                            text="Ответить на лайк:",
                            reply_markup=_respond_kb(viewer_profile_id, int(tg.id)),
                        )
                    except Exception:
                        # Best-effort: notification is optional.
                        pass
        else:
            await safe_callback_answer(call, "Пропуск")

        if res.get("is_match"):
            await safe_callback_answer(call, "Мэтч!")
            if call.message:
                await safe_answer(
                    call.message,
                    "У вас мэтч! Можешь написать человеку в Telegram, если знаешь его контакт.",
                )
            if target_tg_id:
                await safe_send_to_telegram_id(
                    target_tg_id,
                    "У вас мэтч! Откройте бота и посмотрите ленту.",
                )

        if call.message:
            nxt = res.get("next")
            if not nxt:
                await safe_answer(
                    call.message,
                    "Анкеты закончились (или пока больше нет доступных анкет).",
                )
                return
            await safe_answer(
                call.message,
                _format_feed_card(nxt),
                reply_markup=_feed_kb(nxt["profile_id"], int(nxt["telegram_id"])),
            )

    @dp.callback_query(F.data.startswith("resp:"))
    async def on_like_response(call: CallbackQuery) -> None:
        """
        Reaction to a received like: like back or skip.
        callback_data: resp:<action>:<to_profile_id>:<from_telegram_id>
        """
        tg = call.from_user
        if tg is None:
            return
        parts = (call.data or "").split(":")
        if len(parts) < 4:
            await safe_callback_answer(call, "Кнопка устарела.")
            return
        _, action, to_profile_id, from_tg_raw = parts[0], parts[1], parts[2], parts[3]
        try:
            from_tg_id = int(from_tg_raw)
        except Exception:
            from_tg_id = 0

        try:
            res = await api.interact(telegram_id=tg.id, to_profile_id=to_profile_id, action=action)
        except Exception:
            logger.exception("Failed to respond to like")
            await safe_callback_answer(call, "Не получилось отправить ответ. Попробуй позже.")
            return

        if action == "like":
            await safe_callback_answer(call, "Отправлено: взаимно")
        else:
            await safe_callback_answer(call, "Ок")

        if res.get("is_match"):
            if call.message:
                await safe_answer(call.message, "У вас мэтч!")
            if from_tg_id:
                await safe_send_to_telegram_id(from_tg_id, "У вас мэтч! Откройте бота.")

    @dp.callback_query(F.data.startswith("menu:"))
    async def on_menu_action(call: CallbackQuery) -> None:
        tg = call.from_user
        if tg is None:
            return
        action = (call.data or "").split(":", 1)[1] if call.data else ""
        if action == "profile":
            await call.answer()
            if call.message:
                state = dp.fsm.get_context(bot=bot, chat_id=call.message.chat.id, user_id=tg.id)
                await profile_start(call.message, state=state)
            return
        if action == "me":
            await call.answer()
            if call.message:
                await me(call.message)
            return
        if action == "feed":
            await call.answer()
            if call.message:
                await feed(call.message)
            return
        if action == "help":
            await call.answer()
            if call.message:
                await help_cmd(call.message)
            return

        await call.answer("Неизвестная кнопка")

    try:
        await dp.start_polling(bot)
    finally:
        await api.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
