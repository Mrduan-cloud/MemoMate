"""Tests for stackoverflow MCP server.

纯逻辑(sort 归一、URL 构造、问题/答案归一、HTML→纯文本、年龄人类可读)默认跑,用贴合
真实 Stack Exchange API 响应形状的 fixture 验证;live 网络测试带 @network 标记默认跳过
(`pytest -m network` 跑真站,消耗匿名配额)。
"""

from __future__ import annotations

import pytest

from servers.stackoverflow.server import (
    _answers_url,
    _html_to_text,
    _humanize_age,
    _normalize_answer,
    _normalize_question,
    _normalize_sort,
    _parse_items,
    _search_url,
    get_stackoverflow_answers,
    search_stackoverflow,
)

# 贴合真实 /search/advanced 单条 item 形状
_Q_ACCEPTED = {
    "tags": ["python", "python-asyncio"],
    "owner": {"display_name": "alice"},
    "is_answered": True,
    "view_count": 12000,
    "accepted_answer_id": 42,          # 有被采纳答案 → 字段存在
    "answer_count": 5,
    "score": 388,
    "creation_date": 1_600_000_000,
    "question_id": 11236129,
    "link": "https://stackoverflow.com/questions/11236129/how-does-asyncio-work",
    "title": "How does asyncio actually work &amp; why?",   # 含 HTML 实体
}
_Q_UNACCEPTED = {                      # 无被采纳答案 → accepted_answer_id 字段缺失
    "tags": ["python", "sqlalchemy"],
    "owner": {"display_name": "bob"},
    "is_answered": False,
    "view_count": 30,
    "answer_count": 0,
    "score": 0,
    "creation_date": 1_600_000_000,
    "question_id": 78984714,
    "link": "https://stackoverflow.com/questions/78984714/x",
    "title": "asyncio gather with sqlalchemy session",
}

# 贴合真实 /questions/{id}/answers?filter=withbody 形状(answer 不含 link 字段)
_A_ACCEPTED = {
    "owner": {"display_name": "Yurii Motov"},
    "is_accepted": True,
    "score": 17,
    "creation_date": 1_600_000_000,
    "answer_id": 78985000,
    "question_id": 78984714,
    "body": "<p>The only way is to use <code>use_cache=False</code>.</p>\n"
            "<pre><code>session_a = Depends(get_session)\nsession_b = Depends(get_session)</code></pre>",
}
_A_NO_ID = {"score": 3, "body": "<p>no id here</p>"}  # 无 answer_id → 跳过


# ---------- _normalize_sort ----------
def test_normalize_sort_passthrough_alias_default() -> None:
    assert _normalize_sort("votes") == "votes"
    assert _normalize_sort("RELEVANCE") == "relevance"
    assert _normalize_sort("高赞") == "votes"
    assert _normalize_sort("newest") == "creation"
    assert _normalize_sort("活跃") == "activity"
    assert _normalize_sort("garbage") == "relevance"     # 未知归 relevance


# ---------- url 构造 ----------
def test_search_url_encodes_clamps_and_tags() -> None:
    url = _search_url("asyncio gather", tag="python", limit=999, sort="高赞")
    assert url.startswith("https://api.stackexchange.com/2.3/search/advanced?")
    assert "q=asyncio+gather" in url
    assert "tagged=python" in url
    assert "sort=votes" in url
    assert "site=stackoverflow" in url
    assert "pagesize=30" in url          # clamp 上限 30


def test_search_url_omits_empty_tag() -> None:
    assert "tagged=" not in _search_url("x", tag="", limit=5, sort="relevance")


def test_answers_url_clamps_and_withbody() -> None:
    url = _answers_url(78984714, limit=999)
    assert url.startswith("https://api.stackexchange.com/2.3/questions/78984714/answers?")
    assert "filter=withbody" in url
    assert "sort=votes" in url
    assert "pagesize=10" in url          # clamp 上限 10


# ---------- _humanize_age ----------
@pytest.mark.parametrize("seconds,expected", [
    (None, None), (-5, None), (30, "1m"), (1800, "30m"), (7200, "2h"), (90000, "1d"),
])
def test_humanize_age(seconds, expected) -> None:
    assert _humanize_age(seconds) == expected


# ---------- _html_to_text ----------
def test_html_to_text_unescapes_strips_and_keeps_code() -> None:
    out = _html_to_text(_A_ACCEPTED["body"])
    assert "use_cache=False" in out
    assert "session_a = Depends(get_session)" in out  # 代码块文本保留
    assert "<code>" not in out and "<pre>" not in out  # 标签去净
    # 块级标签换行:正文段与代码块不黏在一行
    assert "use_cache=False." in out


def test_html_to_text_entities_and_empty() -> None:
    assert _html_to_text("<p>a &amp; b &lt;tag&gt;</p>") == "a & b <tag>"
    assert _html_to_text("") == ""
    assert _html_to_text("<script>evil()</script>hi") == "hi"


def test_html_to_text_preserves_code_indentation() -> None:
    """回归:<pre> 代码块的行首缩进必须保留(SO 是代码站,缩进有语义)。"""
    body = ('<p>Define it:</p>\n'
            '<pre class="lang-py"><code>def foo():\n'
            '    if x:\n'
            '        return 1\n'
            '    return 0\n'
            '</code></pre>')
    out = _html_to_text(body)
    assert out.startswith("Define it:")        # 段落文字仍正常归一
    assert "def foo():" in out
    assert "\n    if x:" in out                 # 4-space 缩进保留
    assert "\n        return 1" in out          # 8-space 缩进保留
    assert "<pre>" not in out and "<code>" not in out


def test_html_to_text_pre_unescapes_and_multiple_blocks() -> None:
    """<pre> 内实体解码 + 缩进保留 + 多个代码块都各自还原。"""
    body = ("<pre><code>if a &lt; b:\n    x &amp;= 1</code></pre>\n"
            "<p>then</p>\n<pre><code>y = 2</code></pre>")
    out = _html_to_text(body)
    assert "if a < b:" in out                   # 实体 &lt; → <
    assert "\n    x &= 1" in out                # 缩进保留 + &amp; → &
    assert "then" in out
    assert "y = 2" in out


# ---------- _normalize_question ----------
def test_normalize_question_accepted() -> None:
    q = _normalize_question(_Q_ACCEPTED, now_epoch=_Q_ACCEPTED["creation_date"] + 7200)
    assert q["id"] == 11236129
    assert q["title"] == "How does asyncio actually work & why?"   # 实体解码
    assert q["score"] == 388
    assert q["answers"] == 5
    assert q["is_answered"] is True
    assert q["accepted"] is True
    assert q["tags"] == ["python", "python-asyncio"]
    assert q["views"] == 12000
    assert q["age"] == "2h"
    assert q["link"].startswith("https://stackoverflow.com/questions/11236129")


def test_normalize_question_unaccepted_field_absent() -> None:
    q = _normalize_question(_Q_UNACCEPTED, now_epoch=_Q_UNACCEPTED["creation_date"] + 100)
    assert q["accepted"] is False        # accepted_answer_id 缺失 → False
    assert q["is_answered"] is False


def test_normalize_question_link_fallback() -> None:
    raw = dict(_Q_ACCEPTED)
    del raw["link"]
    q = _normalize_question(raw, now_epoch=raw["creation_date"])
    assert q["link"] == "https://stackoverflow.com/q/11236129"


@pytest.mark.parametrize("raw", [None, {}, "nope", {"question_id": 1}, {"title": "t"}])
def test_normalize_question_rejects_bad(raw) -> None:
    assert _normalize_question(raw, now_epoch=1_700_000_000.0) is None


# ---------- _normalize_answer ----------
def test_normalize_answer_shapes_and_link() -> None:
    a = _normalize_answer(_A_ACCEPTED, now_epoch=_A_ACCEPTED["creation_date"] + 86400)
    assert a["id"] == 78985000
    assert a["score"] == 17
    assert a["is_accepted"] is True
    assert a["author"] == "Yurii Motov"
    assert "use_cache=False" in a["body"]
    assert a["link"] == "https://stackoverflow.com/a/78985000"   # 构造的规范短链
    assert a["age"] == "1d"


def test_normalize_answer_missing_owner_and_id() -> None:
    assert _normalize_answer(_A_NO_ID, now_epoch=1_700_000_000.0) is None
    a = _normalize_answer({"answer_id": 5, "body": "<p>x</p>"}, now_epoch=1_700_000_000.0)
    assert a["author"] is None           # owner 缺失 → None,不崩


# ---------- _parse_items ----------
def test_parse_items_search_skips_bad_and_limits() -> None:
    payload = {"items": [_Q_ACCEPTED, {"question_id": None}, _Q_UNACCEPTED]}
    out = _parse_items(payload, limit=15, now_epoch=1_700_000_000.0, normalize=_normalize_question)
    assert [q["id"] for q in out] == [11236129, 78984714]   # 无 id 的被跳过
    assert _parse_items(payload, limit=1, now_epoch=1_700_000_000.0,
                        normalize=_normalize_question)[0]["id"] == 11236129


def test_parse_items_answers_and_garbage() -> None:
    payload = {"items": [_A_ACCEPTED, _A_NO_ID]}
    out = _parse_items(payload, limit=15, now_epoch=1_700_000_000.0, normalize=_normalize_answer)
    assert len(out) == 1 and out[0]["id"] == 78985000       # 无 answer_id 的被跳过
    assert _parse_items(None, limit=5, now_epoch=0.0, normalize=_normalize_answer) == []
    assert _parse_items({"items": "nope"}, limit=5, now_epoch=0.0,
                        normalize=_normalize_question) == []


# ---------- 工具入口:空/非法输入优雅降级(不联网) ----------
def test_search_empty_query_returns_empty() -> None:
    assert search_stackoverflow("   ") == []


@pytest.mark.parametrize("bad", [0, -3, "x", None])
def test_get_answers_bad_qid_returns_empty(bad) -> None:
    assert get_stackoverflow_answers(bad) == []


# ---------- live(默认跳过,消耗配额) ----------
@pytest.mark.network
def test_live_search_and_answers() -> None:
    rows = search_stackoverflow("asyncio gather", tag="python", limit=3)
    assert isinstance(rows, list) and len(rows) <= 3
    if rows:
        q = rows[0]
        assert q["title"] and q["link"].startswith("https://stackoverflow.com/")
        if q["answers"]:
            answers = get_stackoverflow_answers(q["id"], limit=2)
            assert isinstance(answers, list) and len(answers) <= 2
            if answers:
                assert answers[0]["link"].startswith("https://stackoverflow.com/a/")
