"""Telegram-хендлеры для взаимодействия с пользователем."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.yandex_music_service import YandexMusicService, render_metadata_message


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
        del context
        if update.message is None or not update.message.text:
            return

        url = update.message.text.strip()

        try:
            metadata = service.get_metadata_by_url(url)
            response = render_metadata_message(metadata)
            await update.message.reply_text(response)
        except ValueError as exc:
            await update.message.reply_text(f"Ошибка: {exc}")
        except Exception:
            await update.message.reply_text(
                "Не удалось получить данные трека. Попробуйте позже."
            )

    return handle_track_link

