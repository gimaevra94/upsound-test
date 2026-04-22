"""Простая реализация TTL-кеша, используемая сервисом метаданных."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class _CacheEntry(Generic[V]):
    """Внутренний контейнер: значение + время истечения."""

    value: V
    expires_at: float


class TTLCache(Generic[K, V]):
    """
    In-memory key-value кеш с TTL на весь кеш.

    Класс специально сделан маленьким и явным, чтобы его было легко тестировать
    и использовать без внешних зависимостей.
    """

    def __init__(self, ttl_seconds: int, time_func=time.time) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero.")
        self._ttl_seconds = ttl_seconds
        self._time_func = time_func
        self._entries: dict[K, _CacheEntry[V]] = {}

    def get(self, key: K) -> V | None:
        """Вернуть значение из кеша, если ключ есть и запись не протухла."""

        entry = self._entries.get(key)
        if entry is None:
            return None
#11
        if entry.expires_at <= self._time_func():
            del self._entries[key]
            return None

        return entry.value

    def set(self, key: K, value: V) -> None:
        """Сохранить значение и вычислить время истечения от текущих часов."""

        self._entries[key] = _CacheEntry(
            value=value,
            expires_at=self._time_func() + self._ttl_seconds,
        )

