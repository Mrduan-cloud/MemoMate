"""Tests for the zhihu_search 24h result cache.

Pure helpers (`cache_key`, `is_fresh`) need no I/O; the SQLite layer is exercised
against a throwaway file under pytest's `tmp_path`. All run by default (no network).
"""

from __future__ import annotations

from servers.zhihu_search.cache import ResultCache, cache_key, is_fresh

DAY = 24 * 3600


# ---------- cache_key ----------
def test_cache_key_is_deterministic() -> None:
    assert cache_key("LangGraph", "question", 5) == cache_key("LangGraph", "question", 5)


def test_cache_key_distinguishes_kind_limit_query() -> None:
    base = cache_key("x", "question", 5)
    assert base != cache_key("x", "answer", 5)
    assert base != cache_key("x", "question", 10)
    assert base != cache_key("y", "question", 5)


def test_cache_key_strips_query_whitespace() -> None:
    assert cache_key("  RAG 评测 ", "answer", 3) == cache_key("RAG 评测", "answer", 3)


# ---------- is_fresh ----------
def test_is_fresh_within_ttl() -> None:
    assert is_fresh(stored_at=1000.0, now=1000.0 + DAY - 1, ttl=DAY) is True


def test_is_fresh_at_and_beyond_ttl() -> None:
    assert is_fresh(1000.0, 1000.0 + DAY, DAY) is False  # exactly ttl → stale
    assert is_fresh(1000.0, 1000.0 + DAY + 1, DAY) is False


def test_is_fresh_future_timestamp_is_stale() -> None:
    # clock skew: stored "in the future" → negative age → not trusted
    assert is_fresh(2000.0, 1000.0, DAY) is False


# ---------- ResultCache roundtrip ----------
def test_cache_put_then_get_roundtrip(tmp_path) -> None:
    c = ResultCache(path=tmp_path / "z.db", ttl=DAY)
    rows = [{"kind": "question", "id": 1, "title": "如何评价 LangGraph？"}]
    c.put("k", rows, now=1000.0)
    assert c.get("k", now=1000.0 + 10) == rows


def test_cache_miss_returns_none(tmp_path) -> None:
    c = ResultCache(path=tmp_path / "z.db")
    assert c.get("never-stored") is None


def test_cache_stale_entry_returns_none(tmp_path) -> None:
    c = ResultCache(path=tmp_path / "z.db", ttl=DAY)
    c.put("k", [{"id": 1}], now=1000.0)
    # 25h later → past the 24h TTL → miss
    assert c.get("k", now=1000.0 + DAY + 3600) is None


def test_cache_upsert_overwrites(tmp_path) -> None:
    c = ResultCache(path=tmp_path / "z.db", ttl=DAY)
    c.put("k", [{"v": 1}], now=1000.0)
    c.put("k", [{"v": 2}], now=1001.0)
    assert c.get("k", now=1002.0) == [{"v": 2}]


def test_cache_preserves_unicode(tmp_path) -> None:
    c = ResultCache(path=tmp_path / "z.db", ttl=DAY)
    rows = [{"title": "状态机设计 · 多智能体", "author": "张三"}]
    c.put("k", rows, now=1000.0)
    assert c.get("k", now=1000.0) == rows
