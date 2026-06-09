"""Tests for bilibili_search MCP server.

Network-dependent tests are marked and skipped by default; run with
`pytest -m network` to exercise the live B站 API.
"""

from __future__ import annotations

import pytest

from servers.bilibili_search.server import (
    _extract_aid_cid,
    _extract_bvid,
    _normalize_url,
    _parse_subtitle_body,
    _parse_subtitle_list,
    _pick_subtitle,
    _player_api_url,
    _segments_to_text,
    _sessdata,
    _strip_html,
)


def test_strip_html_removes_em_keyword_tags() -> None:
    raw = '<em class="keyword">LangGraph</em> 教程合集'
    assert _strip_html(raw) == "LangGraph 教程合集"


def test_strip_html_decodes_entities() -> None:
    assert _strip_html("AT&amp;T 与 &lt;script&gt;") == "AT&T 与 <script>"


def test_strip_html_empty() -> None:
    assert _strip_html("") == ""


def test_bvid_regex_matches_in_url() -> None:
    import re

    m = re.search(r"(BV[0-9A-Za-z]{10})", "https://www.bilibili.com/video/BV1xx411c7mD/?spm=foo")
    assert m is not None
    assert m.group(1) == "BV1xx411c7mD"


# ---------- subtitles: pure-function unit tests (offline) ----------
def test_extract_bvid_bare_and_url() -> None:
    assert _extract_bvid("BV1xx411c7mD") == "BV1xx411c7mD"
    assert _extract_bvid("https://www.bilibili.com/video/BV1xx411c7mD/?p=2") == "BV1xx411c7mD"


def test_extract_bvid_invalid_raises() -> None:
    with pytest.raises(ValueError):
        _extract_bvid("not-a-video")


def test_normalize_url_protocol_relative() -> None:
    assert _normalize_url("//i0.hdslb.com/bfs/subtitle/x.json") == "https://i0.hdslb.com/bfs/subtitle/x.json"
    assert _normalize_url("https://x/y.json") == "https://x/y.json"
    assert _normalize_url("") == ""


def test_player_api_url_carries_ids() -> None:
    url = _player_api_url(12345, 67890)
    assert url.startswith("https://api.bilibili.com/x/player/v2?")
    assert "aid=12345" in url and "cid=67890" in url


def test_extract_aid_cid_single_part() -> None:
    payload = {"data": {"aid": 111, "cid": 222, "pages": []}}
    assert _extract_aid_cid(payload) == (111, 222)


def test_extract_aid_cid_multi_part_picks_and_clamps() -> None:
    payload = {"data": {"aid": 111, "cid": 999,
                        "pages": [{"cid": 10}, {"cid": 20}, {"cid": 30}]}}
    assert _extract_aid_cid(payload, part=2) == (111, 20)
    # part out of range clamps to the last page (not the top-level cid)
    assert _extract_aid_cid(payload, part=99) == (111, 30)
    # part below 1 clamps to the first page
    assert _extract_aid_cid(payload, part=0) == (111, 10)


def test_extract_aid_cid_missing_raises() -> None:
    with pytest.raises(ValueError):
        _extract_aid_cid({"data": {"aid": 111, "cid": None, "pages": []}})


def _player_payload() -> dict:
    return {
        "data": {
            "subtitle": {
                "subtitles": [
                    {"lan": "ai-zh", "lan_doc": "中文（自动）",
                     "subtitle_url": "//i0.hdslb.com/bfs/subtitle/ai.json"},
                    {"lan": "zh-CN", "lan_doc": "中文（中国）",
                     "subtitle_url": "//i0.hdslb.com/bfs/subtitle/human.json"},
                ]
            }
        }
    }


def test_parse_subtitle_list_flags_ai_and_absolutizes_url() -> None:
    subs = _parse_subtitle_list(_player_payload())
    assert len(subs) == 2
    ai, human = subs[0], subs[1]
    assert ai["lan"] == "ai-zh" and ai["is_ai"] is True
    assert human["lan"] == "zh-CN" and human["is_ai"] is False
    assert human["url"].startswith("https://i0.hdslb.com/")


def test_parse_subtitle_list_empty() -> None:
    assert _parse_subtitle_list({}) == []
    assert _parse_subtitle_list({"data": {"subtitle": {}}}) == []


def test_pick_subtitle_prefers_exact_lang() -> None:
    subs = _parse_subtitle_list(_player_payload())
    assert _pick_subtitle(subs, "zh-CN")["lan"] == "zh-CN"


def test_pick_subtitle_prefix_match() -> None:
    subs = _parse_subtitle_list(_player_payload())
    # "zh" should prefix-match "zh-CN" (human), not "ai-zh"
    assert _pick_subtitle(subs, "zh")["lan"] == "zh-CN"


def test_pick_subtitle_prefers_human_when_no_lang() -> None:
    subs = _parse_subtitle_list(_player_payload())
    assert _pick_subtitle(subs, None)["lan"] == "zh-CN"


def test_pick_subtitle_none_when_empty() -> None:
    assert _pick_subtitle([], "zh-CN") is None


def test_parse_subtitle_body_and_text() -> None:
    body = {"body": [
        {"from": 0.0, "to": 2.0, "content": " 你好 "},
        {"from": 2.0, "to": 4.0, "content": "世界"},
        {"from": 4.0, "to": 5.0, "content": ""},  # blank dropped from text
    ]}
    segs = _parse_subtitle_body(body)
    assert len(segs) == 3
    assert segs[0]["content"] == "你好"  # trimmed
    assert _segments_to_text(segs) == "你好\n世界"


def test_sessdata_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BILIBILI_SESSDATA", raising=False)
    assert _sessdata() is None
    monkeypatch.setenv("BILIBILI_SESSDATA", "  abc123  ")
    assert _sessdata() == "abc123"  # trimmed


# ---------- live network tests (deselected by default) ----------
@pytest.mark.network
def test_search_bilibili_videos_live() -> None:
    """Live integration test — requires network access to api.bilibili.com."""
    from servers.bilibili_search.server import search_bilibili_videos

    results = search_bilibili_videos("LangChain", limit=3)
    assert isinstance(results, list)
    assert len(results) >= 1
    first = results[0]
    assert first["bvid"].startswith("BV")
    assert first["title"]
    assert first["url"].startswith("https://www.bilibili.com/video/")


@pytest.mark.network
def test_get_video_info_live() -> None:
    """Live integration test for get_video_info."""
    from servers.bilibili_search.server import get_video_info

    # Pick a well-known bvid (CCTV-style channel intro, stable).
    info = get_video_info("BV1GJ411x7h7")
    assert info["bvid"] == "BV1GJ411x7h7"
    assert info["title"]
    assert info["url"].endswith("BV1GJ411x7h7")


@pytest.mark.network
def test_get_video_subtitles_live() -> None:
    """Live subtitle fetch — needs network and BILIBILI_SESSDATA set to a valid
    logged-in cookie, otherwise B站 returns an empty subtitle list (the call
    still degrades gracefully to an error dict rather than raising)."""
    from servers.bilibili_search.server import get_video_subtitles

    out = get_video_subtitles("BV1GJ411x7h7")
    assert isinstance(out, dict)
    assert out["bvid"] == "BV1GJ411x7h7"
    # Either we got segments, or a graceful error dict — never an exception.
    assert "segments" in out or "error" in out
