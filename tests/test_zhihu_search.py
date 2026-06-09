"""Tests for zhihu_search MCP server.

Pure logic (kind clamping, URL building, HTML stripping, search-payload parsing,
rate-limit math) runs by default. The live network test is marked and skipped
by default; run with `pytest -m network` to hit the real 知乎 API.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from servers.zhihu_search import server as zserver
from servers.zhihu_search.server import (
    _build_search_url,
    _normalize_kind,
    _parse_search,
    _RateLimiter,
    _strip_html,
    search_zhihu,
)

# A trimmed-but-realistic search_v3 payload: one question, one answer, and two
# noise rows (knowledge ad + relevant-query) that must be skipped.
SAMPLE = {
    "data": [
        {"type": "relevant_query", "object": {"type": "relevant_query", "queries": []}},
        {
            "type": "search_result",
            "object": {
                "type": "question",
                "id": 12345,
                "title": "如何评价 <em>LangGraph</em>？",
                "excerpt": "一个多智能体编排框架……",
                "answer_count": 42,
            },
        },
        {
            "type": "search_result",
            "object": {
                "type": "answer",
                "id": 98765,
                "excerpt": "LangGraph 的<em>状态机</em>设计……",
                "voteup_count": 100,
                "author": {"name": "张三"},
                "question": {"id": 12345, "title": "如何评价 LangGraph？"},
            },
        },
        {"type": "search_club", "object": {"type": "search_club"}},
    ]
}


# ---------- _normalize_kind ----------
def test_normalize_kind_passthrough() -> None:
    assert _normalize_kind("question") == "question"
    assert _normalize_kind("answer") == "answer"


def test_normalize_kind_case_insensitive() -> None:
    assert _normalize_kind("ANSWER") == "answer"
    assert _normalize_kind("  Question ") == "question"


def test_normalize_kind_fallback() -> None:
    assert _normalize_kind("") == "question"
    assert _normalize_kind("garbage") == "question"
    assert _normalize_kind("article") == "question"  # not user-facing yet


# ---------- _build_search_url ----------
def test_build_search_url_encodes_query_and_params() -> None:
    url = _build_search_url("LangGraph 教程", 5)
    assert url.startswith("https://www.zhihu.com/api/v4/search_v3?")
    assert "t=general" in url
    assert "limit=5" in url
    # Chinese + space must be percent-encoded, not raw
    assert "LangGraph" in url
    assert " " not in url
    assert "教程" not in url  # encoded


# ---------- _strip_html ----------
def test_strip_html_removes_em_tags() -> None:
    assert _strip_html("如何评价 <em>LangGraph</em>？") == "如何评价 LangGraph？"


def test_strip_html_decodes_entities() -> None:
    assert _strip_html("A&amp;B 与 &lt;tag&gt;") == "A&B 与 <tag>"


def test_strip_html_empty() -> None:
    assert _strip_html("") == ""
    assert _strip_html(None) == ""  # type: ignore[arg-type]


# ---------- _parse_search ----------
def test_parse_search_questions_only() -> None:
    res = _parse_search(SAMPLE, "question", 5)
    assert len(res) == 1
    q = res[0]
    assert q["kind"] == "question"
    assert q["id"] == 12345
    assert q["title"] == "如何评价 LangGraph？"  # <em> stripped
    assert q["answer_count"] == 42
    assert q["url"] == "https://www.zhihu.com/question/12345"


def test_parse_search_answers_only() -> None:
    res = _parse_search(SAMPLE, "answer", 5)
    assert len(res) == 1
    a = res[0]
    assert a["kind"] == "answer"
    assert a["author"] == "张三"
    assert a["voteup_count"] == 100
    assert a["url"] == "https://www.zhihu.com/question/12345/answer/98765"


def test_parse_search_skips_noise_rows() -> None:
    # relevant_query / search_club rows must never appear as results
    assert _parse_search(SAMPLE, "question", 5) != []
    kinds = {r["kind"] for r in _parse_search(SAMPLE, "question", 5)}
    assert kinds == {"question"}


def test_parse_search_respects_limit() -> None:
    payload = {
        "data": [
            {"object": {"type": "question", "id": i, "title": f"Q{i}"}} for i in range(10)
        ]
    }
    assert len(_parse_search(payload, "question", 3)) == 3


def test_parse_search_empty_payload() -> None:
    assert _parse_search({}, "question", 5) == []
    assert _parse_search({"data": []}, "answer", 5) == []


# ---------- _RateLimiter (pure math) ----------
def test_rate_limiter_no_wait_when_idle() -> None:
    rl = _RateLimiter(2.0)  # _last defaults to 0.0
    assert rl.wait_seconds(100.0) == 0.0  # long past → no wait


def test_rate_limiter_waits_within_interval() -> None:
    rl = _RateLimiter(2.0)
    rl._last = 100.0
    assert rl.wait_seconds(100.5) == pytest.approx(1.5)
    assert rl.wait_seconds(101.9) == pytest.approx(0.1)


def test_rate_limiter_no_wait_after_interval() -> None:
    rl = _RateLimiter(2.0)
    rl._last = 100.0
    assert rl.wait_seconds(102.0) == 0.0
    assert rl.wait_seconds(105.0) == 0.0


# ---------- search_zhihu end-to-end with mocked HTTP (offline) ----------
class _FakeResp:
    """Minimal context-manager HTTP response wrapping fixed JSON bytes."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


class _FakeOpener:
    """Stand-in for the urllib opener: records calls, returns canned bytes.

    If ``error`` is set, ``open`` raises it to exercise graceful degradation.
    """

    def __init__(self, payload: dict, calls: list, error: Exception | None = None) -> None:
        self._bytes = json.dumps(payload).encode("utf-8")
        self._calls = calls
        self._error = error

    def open(self, req: object, timeout: float | None = None) -> _FakeResp:
        self._calls.append(getattr(req, "full_url", req))
        if self._error is not None:
            raise self._error
        return _FakeResp(self._bytes)


class _DictCache:
    """In-memory cache stub so tests never touch the real ~/.memomate SQLite db."""

    def __init__(self) -> None:
        self.store: dict = {}

    def get(self, key: str):
        return self.store.get(key)

    def put(self, key: str, value) -> None:
        self.store[key] = value


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch):
    """Neutralize the network + sleep + real cache; yield a calls recorder.

    Returns a helper that installs a fake opener (optionally erroring) and the
    shared ``calls`` list so a test can assert how many HTTP hits happened.
    """
    calls: list = []
    cache = _DictCache()
    monkeypatch.setattr(zserver, "_cache", cache)
    monkeypatch.setattr(zserver._limiter, "acquire", lambda: None)  # no real 2s sleep

    def install(payload: dict, error: Exception | None = None) -> None:
        monkeypatch.setattr(
            zserver, "_new_opener", lambda *a, **k: _FakeOpener(payload, calls, error)
        )

    install.calls = calls  # type: ignore[attr-defined]
    install.cache = cache  # type: ignore[attr-defined]
    return install


def test_search_zhihu_hit_path_parses_and_caches(offline) -> None:
    offline(SAMPLE)
    results = search_zhihu("LangGraph", kind="question", limit=5)

    assert len(results) == 1
    assert results[0]["id"] == 12345
    assert results[0]["title"] == "如何评价 LangGraph？"  # <em> stripped end-to-end
    # one network hit, and the non-empty result was cached
    assert len(offline.calls) == 1
    assert offline.cache.store  # cache populated


def test_search_zhihu_second_call_served_from_cache(offline) -> None:
    offline(SAMPLE)
    first = search_zhihu("LangGraph", kind="question", limit=5)
    second = search_zhihu("LangGraph", kind="question", limit=5)

    assert first == second
    # second call must NOT hit the network again
    assert len(offline.calls) == 1


def test_search_zhihu_network_error_degrades_to_empty(offline) -> None:
    offline(SAMPLE, error=urllib.error.URLError("boom"))
    results = search_zhihu("LangGraph", kind="question", limit=5)

    assert results == []
    # failure is not cached (so a later call can retry)
    assert offline.cache.store == {}


def test_search_zhihu_empty_results_not_cached(offline) -> None:
    # payload with no question objects → parsed result is empty
    offline({"data": [{"object": {"type": "answer", "id": 1}}]})
    results = search_zhihu("nothing", kind="question", limit=5)

    assert results == []
    assert offline.cache.store == {}  # empty not cached
    # a retry therefore hits the network again
    search_zhihu("nothing", kind="question", limit=5)
    assert len(offline.calls) == 2


# ---------- live (network) ----------
@pytest.mark.network
def test_search_zhihu_live() -> None:
    """Live integration — requires network to www.zhihu.com (may be blocked)."""
    from servers.zhihu_search.server import search_zhihu

    results = search_zhihu("LangChain", kind="question", limit=3)
    # 知乎 may anti-bot block from CI IPs → empty list is an acceptable outcome;
    # we only assert the contract (always a list; well-formed items if any).
    assert isinstance(results, list)
    for r in results:
        assert r["kind"] == "question"
        assert "zhihu.com/question/" in r["url"]
