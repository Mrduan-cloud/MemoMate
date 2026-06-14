"""Tests for hackernews MCP server.

纯逻辑(分类归一、URL 构造、item/搜索结果归一、年龄人类可读)默认跑,用贴合真实
HN Firebase / Algolia 响应形状的 fixture 验证;live 网络测试带 @network 标记默认跳过
(`pytest -m network` 跑真站)。
"""

from __future__ import annotations

import pytest

from servers.hackernews.server import (
    _humanize_age,
    _item_endpoint,
    _normalize_category,
    _normalize_item,
    _parse_search,
    _search_url,
    _stories_endpoint,
    _to_int,
    get_hackernews_stories,
    search_hackernews,
)

# 贴合真实 /v0/item/{id}.json 形状的 fixture
_STORY = {
    "by": "dhouston", "descendants": 71, "id": 8863, "kids": [9224, 8917],
    "score": 104, "time": 1175714200, "type": "story",
    "title": "My YC app: Dropbox - Throw away your USB drive",
    "url": "http://www.getdropbox.com/u/2/screencast.html",
}
_ASK = {  # Ask HN 帖常无外链
    "by": "tel", "descendants": 16, "id": 121003, "score": 25,
    "text": "...", "time": 1203647620, "type": "story",
    "title": "Ask HN: The Arc Effect",
}
_DELETED = {"id": 99, "deleted": True, "type": "story"}  # 无 title

# 贴合 Algolia /api/v1/search 形状的 fixture
_SEARCH = {
    "hits": [
        {"objectID": "12345", "title": "A fast Rust async runtime",
         "url": "https://example.com/rust-async", "points": 200,
         "author": "alice", "num_comments": 88, "created_at_i": 1600000000},
        {"objectID": "12346", "story_title": "Comment on async",  # 评论命中:无 title,有 story_title
         "url": None, "points": 5, "author": "bob", "num_comments": 0},
        {"objectID": None, "title": "broken hit"},  # 无 objectID → 跳过
    ],
    "nbHits": 2,
}


# ---------- _normalize_category ----------
def test_normalize_category_passthrough_alias_and_default() -> None:
    assert _normalize_category("best") == "best"
    assert _normalize_category("TOP") == "top"
    assert _normalize_category("热门") == "top"
    assert _normalize_category("newest") == "new"
    assert _normalize_category("Ask HN") == "ask"       # 空格 → 去空格 → askhn → ask
    assert _normalize_category("show-hn") == "show"     # 连字符 → showhn → show
    assert _normalize_category("garbage") == "top"      # 未知归 top


# ---------- endpoints / url ----------
def test_stories_endpoint() -> None:
    assert _stories_endpoint("top") == "https://hacker-news.firebaseio.com/v0/topstories.json"
    assert _stories_endpoint("提问") == "https://hacker-news.firebaseio.com/v0/askstories.json"


def test_item_endpoint() -> None:
    assert _item_endpoint(8863) == "https://hacker-news.firebaseio.com/v0/item/8863.json"


def test_search_url_encodes_and_clamps() -> None:
    url = _search_url("rust async", 999)
    assert url.startswith("https://hn.algolia.com/api/v1/search?")
    assert "query=rust+async" in url
    assert "tags=story" in url
    assert "hitsPerPage=50" in url      # clamp 上限


# ---------- _humanize_age ----------
@pytest.mark.parametrize("seconds,expected", [
    (None, None), (-5, None), (30, "1m"), (1800, "30m"), (7200, "2h"), (90000, "1d"),
])
def test_humanize_age(seconds, expected) -> None:
    assert _humanize_age(seconds) == expected


# ---------- _normalize_item ----------
def test_normalize_item_story() -> None:
    item = _normalize_item(_STORY, now_epoch=_STORY["time"] + 7200)
    assert item["id"] == 8863
    assert item["url"] == "http://www.getdropbox.com/u/2/screencast.html"
    assert item["score"] == 104
    assert item["comments"] == 71
    assert item["age"] == "2h"
    assert item["hn_url"] == "https://news.ycombinator.com/item?id=8863"


def test_normalize_item_ask_falls_back_to_hn_url() -> None:
    item = _normalize_item(_ASK, now_epoch=_ASK["time"] + 100)
    assert item["url"] == "https://news.ycombinator.com/item?id=121003"  # 无外链 → HN 讨论页


@pytest.mark.parametrize("raw", [None, {}, _DELETED, "not-a-dict", {"id": 1}])
def test_normalize_item_rejects_bad(raw) -> None:
    assert _normalize_item(raw, now_epoch=1_700_000_000.0) is None


# ---------- _parse_search ----------
def test_parse_search_shapes_and_fallbacks() -> None:
    out = _parse_search(_SEARCH, limit=15)
    assert len(out) == 2                       # 第 3 条无 objectID 被跳过
    assert out[0]["title"] == "A fast Rust async runtime"
    assert out[0]["score"] == 200
    assert out[0]["comments"] == 88
    assert out[1]["title"] == "Comment on async"   # story_title 兜底
    assert out[1]["url"] == "https://news.ycombinator.com/item?id=12346"  # url=None → HN 页
    assert all(it["age"] is None for it in out)


def test_parse_search_limit_and_garbage() -> None:
    assert _parse_search(_SEARCH, limit=1) == _parse_search(_SEARCH, limit=15)[:1]
    assert _parse_search(None, limit=5) == []
    assert _parse_search({"hits": "nope"}, limit=5) == []


# ---------- _to_int ----------
@pytest.mark.parametrize("val,expected", [("123", 123), (45, 45), ("x", None), (None, None)])
def test_to_int(val, expected) -> None:
    assert _to_int(val) == expected


# ---------- live(默认跳过) ----------
@pytest.mark.network
def test_live_top_stories() -> None:
    rows = get_hackernews_stories("top", limit=3)
    assert isinstance(rows, list) and len(rows) <= 3
    if rows:
        r = rows[0]
        assert r["title"] and r["url"] and r["hn_url"].startswith("https://news.ycombinator.com/item?id=")


@pytest.mark.network
def test_live_search() -> None:
    rows = search_hackernews("python", limit=3)
    assert isinstance(rows, list) and len(rows) <= 3
    if rows:
        assert rows[0]["title"]
