"""Точка входа для Telegram-бота."""

from __future__ import annotations

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot.cache import TTLCache
from bot.config import Settings
from bot.handlers import create_lyrics_callback_handler, create_start_handler, create_track_handler
from bot.yandex_music_service import TrackMetadata, YandexMusicService


def build_application(settings: Settings) -> Application:
    """
    Собрать и сконфигурировать Telegram-приложение.

    Возврат `Application` из «чистой» функции упрощает тестирование и позволяет
    переиспользовать сборку в разных окружениях.
    """

    cache: TTLCache[str, TrackMetadata] = TTLCache(ttl_seconds=settings.cache_ttl_seconds)
    service = YandexMusicService(
        yandex_token=settings.yandex_music_token,
        lyrics_max_length=settings.lyrics_max_length,
        cache=cache,
    )

    application = Application.builder().token(settings.telegram_token).build()
    application.add_handler(CommandHandler("start", create_start_handler()))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, create_track_handler(service)))
    application.add_handler(
        CallbackQueryHandler(create_lyrics_callback_handler(), pattern=r"^lyrics:")
    )
    return application


def main() -> None:
    """Загрузить настройки из окружения, собрать приложение и запустить polling."""

    settings = Settings.from_env()
    app = build_application(settings)
    app.run_polling()


if __name__ == "__main__":
    main()

