"""Tests for wechat_mp MCP server.

纯逻辑(URL 校验、字段解析、正文抽取、时间格式化、抗截断回退)默认跑,用贴合真实文章页
结构的紧凑 fixture;live 网络测试带 @network 默认跳过(需 WECHAT_TEST_URL,`pytest -m network`)。

fixture 与回退用例直接来自一次真实抓取的实测:微信文章页 3MB+ 常 IncompleteRead 截断尾部,
而 var nickname / var ct / var user_name 在文末 → account 回退 author、publish_time 取
正文前的 create_timestamp,才不会在真实抓取里丢字段。
"""
from __future__ import annotations

import os

import pytest

from servers.wechat_mp.server import (
    _extract_body,
    _format_publish_time,
    _html_to_text,
    fetch_wechat_article,
    is_wechat_article_url,
    parse_article,
)

# 完整页(含文末 var nickname/ct/user_name)
_FULL = """<!DOCTYPE html><html><head>
<meta property="og:title" content="测试标题 Test &amp; Title" />
<meta property="og:description" content="这是摘要" />
<meta property="og:article:author" content="测试作者" />
</head><body>
<h1 class="rich_media_title" id="activity-name">  H1 备用标题  </h1>
<script>window.cgi = { ori_create_time: '1780386489' * 1, create_timestamp: '1780386489' * 1 };</script>
<div class="rich_media_content" id="js_content" style="visibility:hidden;">
  <section><p>第一段。</p><p>第二段 &amp; 实体。</p></section>
  <style>.x{color:red}</style><script>var y=2;</script>
</div>
<div id="content_bottom_area"></div>
<div id="js_temp_bottom_area">尾部工具栏 不应进正文</div>
<script>
var user_name = "gh_test123";
var nickname = htmlDecode("测试公众号");
var ct = "1780386489";
</script>
</body></html>"""

# 截断页:保留 head(og) + 正文前 create_timestamp + 正文,**砍掉文末** var 脚本
_TRUNCATED = _FULL.split('<div id="content_bottom_area">')[0] + '<div id="content_bottom_area"></div>'


# ---------- is_wechat_article_url ----------
@pytest.mark.parametrize("url,ok", [
    ("https://mp.weixin.qq.com/s/2NR2k6jOR2MYorj78pEM7A", True),
    ("http://mp.weixin.qq.com/s?__biz=abc&mid=1&idx=1&sn=x", True),
    ("https://example.com/s/x", False),
    ("mp.weixin.qq.com/s/x", False),          # 无 scheme
    ("", False),
])
def test_is_wechat_article_url(url, ok):
    assert is_wechat_article_url(url) is ok


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/mp.weixin.qq.com/s/x",   # 子串绕过 → 抓云元数据
    "http://localhost/mp.weixin.qq.com/s",
    "http://evil.com/?x=mp.weixin.qq.com/s",
    "http://evil.com/#mp.weixin.qq.com/s/x",
    "https://mp.weixin.qq.com.evil.com/s/x",          # 子域名伪装
    "ftp://mp.weixin.qq.com/s/x",                     # 非 http(s)
    "http://mp.weixin.qq.com/about",                  # 合法 host 但非文章路径
])
def test_url_validation_blocks_ssrf_and_non_article(url):
    # host 必须严格等于 mp.weixin.qq.com 且路径 /s,堵死子串绕过型 SSRF
    assert is_wechat_article_url(url) is False


# ---------- parse_article 完整页 ----------
def test_parse_full_page():
    d = parse_article(_FULL, url="u")
    assert d["title"] == "测试标题 Test & Title"      # og:title + 实体解码
    assert d["account"] == "测试公众号"                # var nickname
    assert d["account_id"] == "gh_test123"
    assert d["author"] == "测试作者"
    assert d["digest"] == "这是摘要"
    assert d["publish_time"] == "2026-06-02 15:48"
    assert "第一段" in d["text"] and "第二段" in d["text"]
    assert "尾部工具栏" not in d["text"]               # content_bottom_area 之后不入正文
    assert d["error"] is None


# ---------- 抗截断:文末 var 缺失时的回退(对应真实 live 失字段 bug) ----------
def test_parse_truncated_falls_back():
    d = parse_article(_TRUNCATED, url="u")
    assert d["account"] == "测试作者"                  # nickname 缺 → 回退 author
    assert d["publish_time"] == "2026-06-02 15:48"     # 取正文前 create_timestamp
    assert "第一段" in d["text"]                        # 正文仍在
    assert d["account_id"] == ""                        # 仅文末有 → 截断时空(best-effort)
    assert d["error"] is None


# ---------- _format_publish_time ----------
@pytest.mark.parametrize("ct,expected", [
    ("1780386489", "2026-06-02 15:48"),   # 实测真实文章发布时刻(北京时间)
    ("", ""),
    ("not-a-number", ""),
    (None, ""),
    ("999999999999999999", ""),           # 超大 epoch → gmtime 越界,兜住返回 ""(不崩)
    ("9" * 30, ""),
])
def test_format_publish_time(ct, expected):
    assert _format_publish_time(ct) == expected


def test_parse_oversized_ct_does_not_crash():
    # ct 来自页面,超大数不应让 parse_article 抛异常(页面可控的崩溃面)
    html = '<meta property="og:title" content="T" /><script>var ct = "99999999999999999999";</script>'
    d = parse_article(html, url="u")
    assert d["publish_time"] == "" and d["error"] is None and d["title"] == "T"


def test_fetch_never_raises_on_parser_error(monkeypatch):
    import servers.wechat_mp.server as srv
    monkeypatch.setattr(srv, "_fetch_html", lambda url, timeout=20.0: "<html>x</html>")
    monkeypatch.setattr(srv, "parse_article", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    d = srv.fetch_wechat_article("https://mp.weixin.qq.com/s/x")
    assert d["error"] is not None and d["title"] == ""   # 解析异常被兜成降级,不冒泡


# ---------- _html_to_text / _extract_body ----------
def test_html_to_text_strips_and_unescapes():
    out = _html_to_text("<p>甲</p><script>x()</script><style>.a{}</style><div>乙 &amp; 丙</div>")
    assert "甲" in out and "乙 & 丙" in out
    assert "x()" not in out and ".a{}" not in out


def test_extract_body_stops_at_sentinel():
    body = _extract_body(_FULL)
    assert "第一段" in body and "第二段" in body
    assert "尾部工具栏" not in body


def test_extract_body_missing_returns_empty():
    assert _extract_body("<html><body>无 js_content</body></html>") == ""


# ---------- 优雅降级 ----------
def test_parse_blocked_or_empty_sets_error():
    d = parse_article("<html><head></head><body>环境异常</body></html>", url="u")
    assert d["error"] is not None
    assert d["title"] == "" and d["text"] == ""


def test_fetch_rejects_non_article_url():
    d = fetch_wechat_article("https://example.com/x")
    assert d["error"] is not None
    assert d["title"] == "" and d["text"] == ""


# ---------- live(默认跳过;需 WECHAT_TEST_URL) ----------
@pytest.mark.network
def test_live_fetch():
    url = os.environ.get("WECHAT_TEST_URL")
    if not url:
        pytest.skip("set WECHAT_TEST_URL to run live wechat fetch")
    d = fetch_wechat_article(url)
    assert d["error"] is None
    assert d["title"] and d["text"]
