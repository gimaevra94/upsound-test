"""Модели конфигурации и вспомогательные функции для бота."""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv  

@dataclass(frozen=True)
class Settings:
    """
    Настройки выполнения (runtime) для бота.

    Класс неизменяемый (`frozen=True`), чтобы тесты были детерминированными и
    чтобы исключить случайные изменения настроек после старта приложения.
    """

    telegram_token: str
    yandex_music_token: str
    lyrics_max_length: int = 500
    cache_ttl_seconds: int = 2678400

    @classmethod
    def from_env(cls) -> "Settings":
        """
        Загрузить настройки из переменных окружения.

        Обязательные переменные:
        - TELEGRAM_BOT_TOKEN
        - YANDEX_MUSIC_TOKEN

        Необязательные переменные:
        - LYRICS_MAX_LENGTH (по умолчанию: 500)
        - CACHE_TTL_SECONDS (по умолчанию: 2678400)
        """

        load_dotenv()
        
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        yandex_music_token = os.getenv("YANDEX_MUSIC_TOKEN")

        if not telegram_token:
            raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN.")
        if not yandex_music_token:
            raise ValueError("Требуется переменная окружения YANDEX_MUSIC_TOKEN.")

        lyrics_max_length = int(os.getenv("LYRICS_MAX_LENGTH", "500"))
        cache_ttl_seconds = int(os.getenv("CACHE_TTL_SECONDS", "2678400"))

        return cls(
            telegram_token=telegram_token,
            yandex_music_token=yandex_music_token,
            lyrics_max_length=lyrics_max_length,
            cache_ttl_seconds=cache_ttl_seconds,
        )

