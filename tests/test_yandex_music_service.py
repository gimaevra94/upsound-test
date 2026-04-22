"""Unit-тесты парсинга URL и функций форматирования текста."""

from bot.yandex_music_service import (
    TrackMetadata,
    YandexMusicService,
    build_lyrics_preview,
    _truncate_lyrics,
    parse_track_url,
    render_metadata_message,
)


def test_parse_track_url_success():
    value = parse_track_url("https://music.yandex.ru/album/12345/track/67890")
    assert value == "67890:12345"


def test_parse_track_url_invalid():
    try:
        parse_track_url("https://example.com/test")
    except ValueError as exc:
        assert "Яндекс Музыки" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid URL")


def test_truncate_lyrics_adds_suffix():
    text = "a" * 80
    truncated = _truncate_lyrics(text, max_length=30)
    assert "[Текст песни сокращен]" in truncated
    assert len(truncated) <= 30


def test_render_metadata_message_contains_lyrics_block():
    metadata = TrackMetadata(
        track_id="1:2",
        title="Song",
        artists=["Artist"],
        album="Album",
        duration_seconds=123.45,
        release_date="2023-01-01",
        genre="rock",
        likes_count=100,
        lyrics="Line 1\nLine 2",
        source_url="https://music.yandex.ru/album/2/track/1",
    )

    message = render_metadata_message(metadata)
    assert "Название: Song" in message
    assert "Текст песни:" in message
    assert "Line 1" in message


def test_build_lyrics_preview_marks_truncated_text():
    preview, is_truncated = build_lyrics_preview("a" * 700, preview_length=500)
    assert is_truncated is True
    assert preview.endswith("[Текст песни сокращен]")


def test_build_lyrics_preview_keeps_short_text():
    preview, is_truncated = build_lyrics_preview("line 1\nline 2", preview_length=500)
    assert is_truncated is False
    assert preview == "line 1\nline 2"


def test_extract_genre_prefers_track_meta_data():
    class Meta:
        genre = "hip-hop"

    class Track:
        meta_data = Meta()
        genre = None

    class Album:
        genre = "rap"

    assert YandexMusicService._extract_genre(Track(), Album()) == "hip-hop"


def test_extract_likes_count_falls_back_to_album():
    class Track:
        likes_count = None

    class Album:
        likes_count = "321"

    assert YandexMusicService._extract_likes_count(Track(), Album()) == 321

