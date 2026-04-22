"""Бизнес-логика получения метаданных из Яндекс Музыки."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from yandex_music import Client

from bot.cache import TTLCache

TRACK_URL_REGEX = re.compile(
    r"^https?://music\.yandex\.(?:ru|com)/album/(?P<album_id>\d+)/track/(?P<track_id>\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TrackMetadata:
    """
    Канонический набор метаданных, который бот отправляет пользователю.

    Хранение в dataclass позволяет возвращать типизированный и тестируемый объект
    из сервисного слоя, а форматирование ответа держать отдельно.
    """

    track_id: str
    title: str
    artists: list[str]
    album: str
    duration_seconds: float
    release_date: str | None
    genre: str | None
    likes_count: int | None
    lyrics: str | None
    source_url: str


def parse_track_url(url: str) -> str:
    """
    Извлечь идентификатор трека Яндекс Музыки из URL.

    `yandex-music` принимает id трека в формате `<track_id>:<album_id>`, поэтому
    нормализуем пользовательскую ссылку в это каноническое значение.
    """

    match = TRACK_URL_REGEX.match(url.strip())
    if not match:
        raise ValueError("Это не похоже на ссылку на трек Яндекс Музыки.")

    album_id = match.group("album_id")
    track_id = match.group("track_id")
    return f"{track_id}:{album_id}"


def _truncate_lyrics(text: str, max_length: int) -> str:
    """
    Обрезать текст песни до безопасного размера сообщения.

    У Telegram есть лимит на размер сообщения, поэтому мы намеренно ограничиваем
    длину текста и добавляем понятный суффикс, если обрезка произошла.
    """

    if len(text) <= max_length:
        return text
    suffix = "\n\n[Текст песни сокращен]"
    allowed = max_length - len(suffix)
    if allowed <= 0:
        return suffix.strip()
    return text[:allowed].rstrip() + suffix


class YandexMusicService:
    """
    Получает метаданные из Яндекс Музыки и применяет кеширование.

    Отдельный сервисный класс делает код удобным для тестирования: Telegram-хендлеры
    зависят от этого класса и не знают ничего про HTTP/SDK `yandex-music`.
    """

    def __init__(
        self,
        yandex_token: str,
        lyrics_max_length: int,
        cache: TTLCache[str, TrackMetadata],
    ) -> None:
        self._client = Client(yandex_token).init()
        self._lyrics_max_length = lyrics_max_length
        self._cache = cache

    def get_metadata_by_url(self, url: str) -> TrackMetadata:
        """Распарсить ссылку, проверить кеш и при необходимости запросить API."""

        track_key = parse_track_url(url)
        cached = self._cache.get(track_key)
        if cached is not None:
            return cached

        metadata = self._fetch_metadata(track_key, source_url=url)
        self._cache.set(track_key, metadata)
        return metadata

    def _fetch_metadata(self, track_key: str, source_url: str) -> TrackMetadata:
        """Вызвать `yandex-music` и преобразовать ответ в `TrackMetadata`."""

        tracks = self._client.tracks([track_key])
        track = tracks[0] if tracks else None
        if track is None:
            raise ValueError("Трек не найден. Проверьте ссылку.")

        artists = [artist.name for artist in (track.artists or []) if getattr(artist, "name", None)]
        album_title = track.albums[0].title if track.albums else "Неизвестный альбом"
        duration_seconds = round((track.duration_ms or 0) / 1000, 2)

        release_date = self._parse_release_date(track.albums[0].release_date if track.albums else None)

        lyrics = self._try_get_lyrics(track)
        if lyrics:
            lyrics = _truncate_lyrics(lyrics, self._lyrics_max_length)

        metadata = TrackMetadata(
            track_id=track_key,
            title=track.title or "Без названия",
            artists=artists or ["Неизвестный исполнитель"],
            album=album_title,
            duration_seconds=duration_seconds,
            release_date=release_date,
            genre=getattr(track, "genre", None),
            likes_count=self._extract_likes_count(track),
            lyrics=lyrics,
            source_url=source_url,
        )
        return metadata

    @staticmethod
    def _parse_release_date(value: str | None) -> str | None:
        """Отформатировать дату релиза в ISO, либо вернуть как есть при неизвестном формате."""

        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return value

    @staticmethod
    def _extract_likes_count(track: Any) -> int | None:
        """Безопасно извлечь число лайков из объекта трека `yandex-music`."""

        likes_count = getattr(track, "likes_count", None)
        if isinstance(likes_count, int):
            return likes_count
        if isinstance(likes_count, str) and likes_count.isdigit():
            return int(likes_count)
        return None

    @staticmethod
    def _try_get_lyrics(track: Any) -> str | None:
        """
        Попробовать загрузить текст песни через supplement трека.

        В разных версиях `yandex-music` текст может быть доступен через разные
        атрибуты, поэтому метод написан «защитно» и проверяет несколько типовых путей.
        """

        if not getattr(track, "lyrics_available", False):
            return None

        supplement = track.get_supplement()
        if supplement is None:
            return None

        lyrics_obj = getattr(supplement, "lyrics", None)
        if lyrics_obj is None:
            return None

        full_text = getattr(lyrics_obj, "full_lyrics", None)
        if isinstance(full_text, str) and full_text.strip():
            return full_text.strip()

        fetch_method = getattr(lyrics_obj, "fetch_lyrics", None)
        if callable(fetch_method):
            fetched = fetch_method()
            if isinstance(fetched, str) and fetched.strip():
                return fetched.strip()

        return None


def render_metadata_message(metadata: TrackMetadata) -> str:
    """Сформировать человекочитаемый текст ответа из `TrackMetadata`."""

    lines = [
        f"Название: {metadata.title}",
        f"Исполнитель(и): {', '.join(metadata.artists)}",
        f"Альбом: {metadata.album}",
        f"Длительность: {metadata.duration_seconds} сек",
        f"Дата релиза: {metadata.release_date or 'Неизвестно'}",
        f"Жанр: {metadata.genre or 'Неизвестно'}",
        f"Лайков: {metadata.likes_count if metadata.likes_count is not None else 'Нет данных'}",
        f"Ссылка: {metadata.source_url}",
    ]

    if metadata.lyrics:
        lines.append("")
        lines.append("Текст песни:")
        lines.append(metadata.lyrics)
    else:
        lines.append("")
        lines.append("Текст песни: отсутствует")

    return "\n".join(lines)

