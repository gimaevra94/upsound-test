"""Бизнес-логика получения метаданных из Яндекс Музыки."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from yandex_music import Client
from yandex_music.exceptions import NotFoundError

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


def build_lyrics_preview(text: str, preview_length: int = 500) -> tuple[str, bool]:
    """Подготовить превью текста песни фиксированной длины."""

    normalized = text.strip()
    if len(normalized) <= preview_length:
        return normalized, False

    preview = normalized[:preview_length].rstrip()
    return f"{preview}\n\n[Текст песни сокращен]", True


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
        primary_album = track.albums[0] if track.albums else None
        album_title = primary_album.title if primary_album and getattr(primary_album, "title", None) else "Неизвестный альбом"
        duration_seconds = round((track.duration_ms or 0) / 1000, 2)

        release_date = self._parse_release_date(primary_album.release_date if primary_album else None)
        genre = self._extract_genre(track, primary_album)
        likes_count = self._extract_likes_count(track, primary_album)

        if primary_album is not None and (genre is None or likes_count is None):
            full_album = self._try_fetch_album(primary_album)
            if full_album is not None:
                genre = genre or self._extract_genre(track, full_album)
                likes_count = likes_count if likes_count is not None else self._extract_likes_count(track, full_album)

        lyrics = self._try_get_lyrics(track)

        metadata = TrackMetadata(
            track_id=track_key,
            title=track.title or "Без названия",
            artists=artists or ["Неизвестный исполнитель"],
            album=album_title,
            duration_seconds=duration_seconds,
            release_date=release_date,
            genre=genre,
            likes_count=likes_count,
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
    def _to_int(value: Any) -> int | None:
        """Преобразовать значение в целое число, если это возможно."""

        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    @classmethod
    def _extract_likes_count(cls, track: Any, album: Any | None = None) -> int | None:
        """
        Безопасно извлечь число лайков.

        В API значение чаще встречается у альбома, поэтому используем каскад fallback:
        track.likes_count -> album.likes_count.
        """

        for source in (track, album):
            if source is None:
                continue
            likes_count = getattr(source, "likes_count", None)
            normalized = cls._to_int(likes_count)
            if normalized is not None:
                return normalized
        return None

    @staticmethod
    def _extract_genre(track: Any, album: Any | None = None) -> str | None:
        """
        Извлечь жанр из наиболее надёжных полей.

        track.genre в объектах `Track` часто отсутствует, зато жанр встречается
        в track.meta_data.genre и album.genre.
        """

        meta_data = getattr(track, "meta_data", None)
        track_meta_genre = getattr(meta_data, "genre", None) if meta_data is not None else None
        track_genre = getattr(track, "genre", None)
        album_genre = getattr(album, "genre", None) if album is not None else None

        for value in (track_meta_genre, track_genre, album_genre):
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _try_fetch_album(self, album: Any) -> Any | None:
        """Попытаться получить полные данные альбома, если в треке поля пустые."""

        album_id = getattr(album, "id", None)
        if album_id is None:
            return None

        albums_method = getattr(self._client, "albums", None)
        if not callable(albums_method):
            return None

        try:
            albums = albums_method([album_id])
            if albums:
                return albums[0]
        except Exception:
            return None

        return None

    def _try_get_lyrics(self, track: Any) -> str | None:
        """
        Попробовать загрузить текст песни.

        `yandex-music` помечает получение текста через supplement как устаревшее,
        поэтому сначала пробуем актуальные методы `get_lyrics`/`tracks_lyrics`.
        """

        track_id = getattr(track, "id", None)

        # 1) Предпочтительный путь: Track.get_lyrics('TEXT') -> TrackLyrics.fetch_lyrics()
        try:
            get_lyrics = getattr(track, "get_lyrics", None)
            if callable(get_lyrics):
                lyrics_obj = get_lyrics("TEXT")
                if lyrics_obj is not None:
                    fetch = getattr(lyrics_obj, "fetch_lyrics", None)
                    if callable(fetch):
                        text = fetch()
                        if isinstance(text, str) and text.strip():
                            return text.strip()
        except NotFoundError:
            return None
        except Exception:
            # Падаем дальше на альтернативные пути.
            pass

        # 2) Альтернатива: Client.tracks_lyrics(track_id, format_='TEXT') -> TrackLyrics.fetch_lyrics()
        if track_id is not None:
            try:
                lyrics_obj = self._client.tracks_lyrics(track_id, format_="TEXT")
                if lyrics_obj is not None:
                    fetch = getattr(lyrics_obj, "fetch_lyrics", None)
                    if callable(fetch):
                        text = fetch()
                        if isinstance(text, str) and text.strip():
                            return text.strip()
            except NotFoundError:
                return None
            except Exception:
                pass

        # 3) Legacy fallback: supplement.lyrics.full_lyrics / fetch_lyrics()
        try:
            if getattr(track, "lyrics_available", False):
                get_supplement = getattr(track, "get_supplement", None)
                if callable(get_supplement):
                    supplement = get_supplement()
                    lyrics_obj = getattr(supplement, "lyrics", None) if supplement is not None else None
                    if lyrics_obj is not None:
                        full_text = getattr(lyrics_obj, "full_lyrics", None)
                        if isinstance(full_text, str) and full_text.strip():
                            return full_text.strip()

                        fetch_method = getattr(lyrics_obj, "fetch_lyrics", None)
                        if callable(fetch_method):
                            fetched = fetch_method()
                            if isinstance(fetched, str) and fetched.strip():
                                return fetched.strip()
        except Exception:
            pass

        return None


def render_metadata_message(metadata: TrackMetadata, include_lyrics: bool = True) -> str:
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

    if not include_lyrics:
        return "\n".join(lines)

    if metadata.lyrics:
        lines.append("")
        lines.append("Текст песни:")
        lines.append(metadata.lyrics)
    else:
        lines.append("")
        lines.append("Текст песни: отсутствует")

    return "\n".join(lines)

