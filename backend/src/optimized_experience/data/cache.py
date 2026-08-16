"""Small TTL cache wrapper so callers depend on this interface, not on cachetools directly."""

from __future__ import annotations

from typing import Callable, Protocol, TypeVar

from cachetools import TTLCache

T = TypeVar("T")


class Cache(Protocol):
    def get_or_set(self, key: str, compute: Callable[[], T]) -> T: ...


class InProcessTTLCache:
    def __init__(self, ttl_seconds: float, maxsize: int = 256) -> None:
        self._store: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

    def get_or_set(self, key: str, compute: Callable[[], T]) -> T:
        if key in self._store:
            return self._store[key]
        value = compute()
        self._store[key] = value
        return value
