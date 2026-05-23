"""SQLite + FTS5 storage backend for MemoMate memories."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path.home() / ".memomate" / "memories.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_db_path(db_path: Path | str | None) -> Path:
    if db_path is not None:
        return Path(db_path)
    env_path = os.environ.get("MEMOMATE_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


class MemoryStore:
    """SQLite-backed memory store with FTS5 full-text search.

    Keeps an `access_count` and `accessed_at` on each memory so future
    iterations can implement recency/frequency-weighted retrieval.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = _resolve_db_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                content      TEXT    NOT NULL,
                tags         TEXT,
                source       TEXT,
                created_at   TEXT    NOT NULL,
                accessed_at  TEXT,
                access_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content,
                tags,
                content='memories',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS memories_ai
                AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content, tags)
                        VALUES (new.id, new.content, COALESCE(new.tags, ''));
                END;

            CREATE TRIGGER IF NOT EXISTS memories_ad
                AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tags)
                        VALUES ('delete', old.id, old.content, COALESCE(old.tags, ''));
                END;

            CREATE TRIGGER IF NOT EXISTS memories_au
                AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tags)
                        VALUES ('delete', old.id, old.content, COALESCE(old.tags, ''));
                    INSERT INTO memories_fts(rowid, content, tags)
                        VALUES (new.id, new.content, COALESCE(new.tags, ''));
                END;
            """
        )
        self._conn.commit()

    def save(
        self,
        content: str,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> int:
        tags_str = ",".join(tags) if tags else None
        cur = self._conn.execute(
            "INSERT INTO memories (content, tags, source, created_at) VALUES (?, ?, ?, ?)",
            (content, tags_str, source, _now_iso()),
        )
        self._conn.commit()
        return cur.lastrowid

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            """
            SELECT m.id, m.content, m.tags, m.source, m.created_at, m.access_count
              FROM memories_fts f
              JOIN memories m ON m.id = f.rowid
             WHERE memories_fts MATCH ?
             ORDER BY rank
             LIMIT ?
            """,
            (query, limit),
        )
        rows = [dict(r) for r in cur.fetchall()]
        if rows:
            ids = tuple(r["id"] for r in rows)
            placeholders = ",".join("?" * len(ids))
            self._conn.execute(
                f"UPDATE memories SET access_count = access_count + 1, accessed_at = ? "
                f"WHERE id IN ({placeholders})",
                (_now_iso(), *ids),
            )
            self._conn.commit()
        return rows

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, content, tags, source, created_at, access_count "
            "FROM memories ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]

    def delete(self, memory_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) AS n FROM memories")
        return cur.fetchone()["n"]

    def close(self) -> None:
        self._conn.close()
