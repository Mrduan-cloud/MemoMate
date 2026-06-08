"""Tests for zhihu_search MCP server.

Pure logic (kind clamping, URL building, HTML stripping, search-payload parsing,
rate-limit math) runs by default. The live network test is marked and skipped
by default; run with `pytest -m network` to hit the real 知乎 API.
"""

from __future__ import annotations

import pytest

from servers.zhihu_search.server import (
    _build_search_url,
    _normalize_kind,
    _parse_search,
    _RateLimiter,
    _strip_html,
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
