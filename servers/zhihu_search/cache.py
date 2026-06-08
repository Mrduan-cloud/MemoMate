"""24h result cache for zhihu_search — stdlib ``sqlite3``, zero dependencies.

知乎 throttles hard, so search results are cached for 24h in a single file
(``~/.memomate/zhihu_cache.db``). Keyed by ``(kind, limit, query)``.

Design:
- ``cache_key`` and ``is_fresh`` are **pure** → unit-testable without I/O.
- ``ResultCache`` is the thin SQLite layer; every op **degrades gracefully**
  (any ``sqlite3`` error → behave as a cache miss / no-op), so a broken cache
  file never breaks search itself.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

DEFAULT_TTL = 24 * 3600  # 24h
DEFAULT_PATH = Path.home() / ".memomate" / "zhihu_cache.db"


def cache_key(query: str, kind: str, limit: int) -> str:
    """Stable cache key for a search. Pure (no I/O)."""
    return f"{kind}:{limit}:{(query or '').strip()}"


def is_fresh(stored_at: float, now: float, ttl: float) -> bool:
    """True iff an entry stored at ``stored_at`` is still within ``ttl`` of ``now``.

    Pure. A future ``stored_at`` (clock skew) yields a negative age → treated as
    stale, so we refetch rather than trust a bogus timestamp.
    """
    age = now - stored_at
    return 0 <= age < ttl


class ResultCache:
    """SQLite-backed 24h cache. All methods swallow ``sqlite3`` errors."""

    def __init__(self, path: str | Path = DEFAULT_PATH, ttl: float = DEFAULT_TTL) -> None:
        self.path = Path(path)
        self.ttl = ttl

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=5)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, payload TEXT NOT NULL, stored_at REAL NOT NULL)"
        )
        return conn

    def get(self, key: str, now: float | None = None) -> list[dict[str, Any]] | None:
        """Return cached results if present and fresh, else ``None`` (miss)."""
        now = time.time() if now is None else now
        try:
            conn = self._connect()
        except sqlite3.Error:
            return None
        try:
            with conn:
                row = conn.execute(
                    "SELECT payload, stored_at FROM cache WHERE key = ?", (key,)
                ).fetchone()
            if row and is_fresh(row[1], now, self.ttl):
                return json.loads(row[0])
            return None
        except (sqlite3.Error, json.JSONDecodeError, TypeError):
            return None
        finally:
            conn.close()

    def put(self, key: str, value: list[dict[str, Any]], now: float | None = None) -> None:
        """Store ``value`` under ``key`` (upsert). No-op on any error."""
        now = time.time() if now is None else now
        try:
            conn = self._connect()
        except sqlite3.Error:
            return
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, payload, stored_at) VALUES (?, ?, ?)",
                    (key, json.dumps(value, ensure_ascii=False), now),
                )
        except (sqlite3.Error, TypeError, ValueError):
            pass
        finally:
            conn.close()
