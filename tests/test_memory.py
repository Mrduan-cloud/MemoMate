"""Smoke tests for the MemoMate core memory store."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.store import MemoryStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmpdir:
        s = MemoryStore(db_path=Path(tmpdir) / "test.db")
        yield s
        s.close()


def test_save_and_recall(store: MemoryStore) -> None:
    mid = store.save("I prefer pnpm over npm", tags=["preference", "tooling"])
    assert mid > 0
    hits = store.search("pnpm")
    assert len(hits) == 1
    assert hits[0]["content"] == "I prefer pnpm over npm"
    assert "preference" in hits[0]["tags"]


def test_list_recent_orders_newest_first(store: MemoryStore) -> None:
    store.save("first")
    store.save("second")
    store.save("third")
    recent = store.list_recent(limit=2)
    assert [r["content"] for r in recent] == ["third", "second"]


def test_delete(store: MemoryStore) -> None:
    mid = store.save("ephemeral")
    assert store.delete(mid) is True
    assert store.delete(mid) is False
    assert store.search("ephemeral") == []


def test_count(store: MemoryStore) -> None:
    assert store.count() == 0
    store.save("a")
    store.save("b")
    assert store.count() == 2


def test_search_with_tag_match(store: MemoryStore) -> None:
    store.save("Docker uses overlay2 by default", tags=["docker", "storage"])
    store.save("Pin PaddleOCR to 2.7+", tags=["mediread"])
    hits = store.search("docker")
    assert len(hits) == 1
    assert "Docker" in hits[0]["content"]


def test_access_count_increments_on_search(store: MemoryStore) -> None:
    store.save("Claude is a good coder")
    store.search("Claude")
    store.search("Claude")
    recent = store.list_recent(limit=1)
    assert recent[0]["access_count"] == 2


def test_wal_mode_is_enabled(store: MemoryStore) -> None:
    """Concurrent-client safety requires WAL — make sure pragma stuck."""
    journal_mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal_mode.lower() == "wal", (
        f"journal_mode is {journal_mode!r}, expected 'wal'. "
        "Multi-client concurrent access depends on this."
    )


def test_busy_timeout_is_configured(store: MemoryStore) -> None:
    """When two writers collide we want to wait, not crash."""
    timeout_ms = store._conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout_ms >= 1000, f"busy_timeout is {timeout_ms} ms, want >= 1000"


def test_concurrent_writers_can_both_complete(tmp_path) -> None:
    """Two MemoryStore instances on the same DB should both write without error."""
    db = tmp_path / "shared.db"
    store_a = MemoryStore(db_path=db)
    store_b = MemoryStore(db_path=db)
    id_a = store_a.save("from client A", tags=["a"])
    id_b = store_b.save("from client B", tags=["b"])
    assert id_a != id_b
    # Either store can see both rows.
    assert store_a.count() == 2
    assert store_b.count() == 2
    store_a.close()
    store_b.close()
