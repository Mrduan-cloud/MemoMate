"""Tests for github_trending MCP server.

纯逻辑(URL 构造、since 归一、HTML 解析)默认跑,用一段贴合真实 GitHub trending 标记的
fixture 验证解析;live 网络测试带 @network 标记默认跳过(`pytest -m network` 跑真站)。
"""

from __future__ import annotations

import pytest

from servers.github_trending.server import (
    _build_url,
    _normalize_since,
    _parse_row,
    _parse_trending,
    _to_int,
    get_github_trending,
)


# 贴合真实 github.com/trending 标记的最小 fixture:2 行(第二行无语言/描述,测兜底)。
def _row(owner_repo: str, *, desc: str | None, lang: str | None,
         total: str, forks: str, period: str) -> str:
    star_svg = '<svg class="octicon octicon-star"><path d="M8 .25"/></svg>'
    fork_svg = '<svg class="octicon octicon-repo-forked"><path d="M5 5.372"/></svg>'
    desc_html = f'<p class="col-9 color-fg-muted my-1 pr-4">\n {desc} \n</p>' if desc else ""
    lang_html = (f'<span itemprop="programmingLanguageColor"></span>'
                 f'<span itemprop="programmingLanguage">{lang}</span>') if lang else ""
    return (
        f'<article class="Box-row">'
        f'<h2 class="h3 lh-condensed"><a href="/{owner_repo}" data-view-component="true">'
        f'{owner_repo}</a></h2>'
        f'{desc_html}'
        f'{lang_html}'
        f'<a href="/{owner_repo}/stargazers" class="Link Link--muted">{star_svg} {total}</a>'
        f'<a href="/{owner_repo}/forks" class="Link Link--muted">{fork_svg} {forks}</a>'
        f'<span class="d-inline-block float-sm-right">{period} stars this week</span>'
        f'</article>'
    )


_FIXTURE = (
    '<div class="Box">'
    + _row("torvalds/linux", desc="Linux kernel source tree", lang="C",
           total="180,123", forks="53,400", period="1,250")
    + _row("acme/no-lang-repo", desc=None, lang=None,
           total="42", forks="3", period="7")
    + "</div>"
)


# ---------- _normalize_since ----------
def test_normalize_since_passthrough_and_alias() -> None:
    assert _normalize_since("weekly") == "weekly"
    assert _normalize_since("WEEKLY") == "weekly"
    assert _normalize_since("本周") == "weekly"
    assert _normalize_since("today") == "daily"
    assert _normalize_since("本月") == "monthly"
    assert _normalize_since("garbage") == "daily"   # 兜底
    assert _normalize_since("") == "daily"


# ---------- _build_url ----------
def test_build_url_no_language() -> None:
    assert _build_url("", "weekly") == "https://github.com/trending?since=weekly"


def test_build_url_with_language_and_alias_since() -> None:
    assert _build_url("python", "今日") == "https://github.com/trending/python?since=daily"


def test_build_url_encodes_special_language() -> None:
    # c++ 必须 URL 编码,不能裸进路径
    url = _build_url("c++", "monthly")
    assert "c%2B%2B" in url and "c++" not in url and url.endswith("since=monthly")


# ---------- _to_int ----------
def test_to_int_handles_commas_and_garbage() -> None:
    assert _to_int("180,123") == 180123
    assert _to_int("42") == 42
    assert _to_int(None) is None
    assert _to_int("—") is None


# ---------- _parse_row / _parse_trending ----------
def test_parse_trending_full_fields() -> None:
    repos = _parse_trending(_FIXTURE, "weekly", limit=10)
    assert len(repos) == 2
    a = repos[0]
    assert a["full_name"] == "torvalds/linux"
    assert a["url"] == "https://github.com/torvalds/linux"
    assert a["description"] == "Linux kernel source tree"
    assert a["language"] == "C"
    assert a["stars"] == 180123 and a["forks"] == 53400
    assert a["stars_in_period"] == 1250


def test_parse_trending_tolerates_missing_lang_and_desc() -> None:
    b = _parse_trending(_FIXTURE, "weekly", limit=10)[1]
    assert b["full_name"] == "acme/no-lang-repo"
    assert b["language"] is None
    assert b["description"] == ""
    assert b["stars"] == 42 and b["stars_in_period"] == 7


def test_parse_trending_respects_limit() -> None:
    assert len(_parse_trending(_FIXTURE, "weekly", limit=1)) == 1


def test_parse_trending_empty_html() -> None:
    assert _parse_trending("", "daily", limit=10) == []
    assert _parse_trending("<html>no rows here</html>", "daily", limit=10) == []


def test_parse_row_without_repo_returns_none() -> None:
    assert _parse_row('<article class="Box-row">no links</article>', "today") is None


# ---------- live (network) ----------
@pytest.mark.network
def test_get_github_trending_live() -> None:
    """Live integration — requires network to github.com (may rate-limit)."""
    repos = get_github_trending(language="python", since="weekly", limit=5)
    assert isinstance(repos, list)
    # 反爬/改版时空列表是可接受降级;有结果则校验契约
    for r in repos:
        assert "/" in r["full_name"]
        assert r["url"].startswith("https://github.com/")
