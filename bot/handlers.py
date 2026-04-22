"""Telegram-хендлеры для взаимодействия с пользователем."""

from __future__ import annotations

import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.yandex_music_service import YandexMusicService, build_lyrics_preview, render_metadata_message

LYRICS_CALLBACK_PREFIX = "lyrics:"
TELEGRAM_TEXT_LIMIT = 4096


def build_start_message() -> str:
    """Вернуть статичный текст для `/start` (вынесен отдельно для удобства тестов)."""

    return (
        "Привет! Отправь ссылку на трек Яндекс Музыки вида:\n"
        "https://music.yandex.ru/album/<album_id>/track/<track_id>\n\n"
        "Я верну подробные метаданные и текст песни (если доступен)."
    )


def create_start_handler():
    """
    Собрать async-хендлер `/start` в виде замыкания.

    Делаем фабрику-замыкание, чтобы в тестах можно было создавать хендлеры
    с изолированными зависимостями.
    """

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if update.message is None:
            return
        await update.message.reply_text(build_start_message())

    return start


def create_track_handler(service: YandexMusicService):
    """
    Собрать async-хендлер сообщений, который обрабатывает ссылки на треки Яндекс Музыки.

    Сервис передаётся снаружи (dependency injection), поэтому хендлер остаётся
    тонким и легко тестируется через заглушки/моки.
    """

    async def handle_track_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or not update.message.text:
            return

        url = update.message.text.strip()

        try:
            metadata = service.get_metadata_by_url(url)
            response = render_metadata_message(metadata, include_lyrics=False)
            keyboard = None

            if metadata.lyrics:
                preview, is_truncated = build_lyrics_preview(metadata.lyrics, preview_length=500)
                response = f"{response}\n\nТекст песни:\n{preview}"

                if is_truncated:
                    callback_id = uuid.uuid4().hex
                    callbacks = context.application.bot_data.setdefault("lyrics_callbacks", {})
                    callbacks[callback_id] = metadata.lyrics
                    keyboard = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "Развернуть полный текст",
                                    callback_data=f"{LYRICS_CALLBACK_PREFIX}{callback_id}",
                                )
                            ]
                        ]
                    )
            else:
                response = f"{response}\n\nТекст песни: отсутствует"

            await update.message.reply_text(response, reply_markup=keyboard)
        except ValueError as exc:
            await update.message.reply_text(f"Ошибка: {exc}")
        except Exception:
            await update.message.reply_text(
                "Не удалось получить данные трека. Попробуйте позже."
            )

    return handle_track_link


def create_lyrics_callback_handler():
    """Собрать callback-хендлер, который отправляет полный текст песни."""

    async def handle_lyrics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return

        callback_id = query.data.removeprefix(LYRICS_CALLBACK_PREFIX)
        callbacks = context.application.bot_data.get("lyrics_callbacks", {})
        lyrics = callbacks.get(callback_id)

        if not lyrics:
            await query.answer("Полный текст больше недоступен.", show_alert=True)
            return

        await query.answer()
        await query.edit_message_reply_markup(reply_markup=None)

        for chunk in _split_text(lyrics, TELEGRAM_TEXT_LIMIT):
            await query.message.reply_text(chunk)

    return handle_lyrics_callback


def _split_text(text: str, chunk_size: int) -> list[str]:
    """Разбить длинный текст на части под лимит Telegram."""

    chunks: list[str] = []
    rest = text.strip()

    while len(rest) > chunk_size:
        split_at = rest.rfind("\n", 0, chunk_size)
        if split_at <= 0:
            split_at = chunk_size
        chunks.append(rest[:split_at].rstrip())
        rest = rest[split_at:].lstrip()

    if rest:
        chunks.append(rest)

    return chunks

