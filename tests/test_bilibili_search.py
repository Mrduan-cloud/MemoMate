"""Tests for bilibili_search MCP server.

Network-dependent tests are marked and skipped by default; run with
`pytest -m network` to exercise the live B站 API.
"""

from __future__ import annotations

import pytest

from servers.bilibili_search.server import _strip_html


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
