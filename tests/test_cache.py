"""Unit-тесты поведения TTL-кеша."""

from bot.cache import TTLCache


def test_cache_returns_value_before_expiration():
    now = [100.0]
    cache = TTLCache[str, int](ttl_seconds=10, time_func=lambda: now[0])

    cache.set("track", 42)
    assert cache.get("track") == 42


def test_cache_expires_values():
    now = [100.0]
    cache = TTLCache[str, int](ttl_seconds=10, time_func=lambda: now[0])

    cache.set("track", 42)
    now[0] = 111.0
    assert cache.get("track") is None

