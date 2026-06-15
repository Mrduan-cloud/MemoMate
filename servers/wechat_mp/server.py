"""MCP server for 微信公众号 public articles (parse a given article URL, no key).

给定一篇**公开**的公众号文章 URL(``mp.weixin.qq.com/s/...`` 或 ``/s?__biz=...``),
抓取并抽取标题 / 公众号 / 作者 / 发布时间 / 正文纯文本。

约定与同仓其它 server 一致:仅标准库(``urllib`` / ``re`` / ``html`` / ``time``)、自我限流
(``_RateLimiter``)、纯解析函数(离线可单测)、优雅降级(网络/解析失败返回**统一形状**的 dict
且带 ``error``,不抛给 MCP client)。

实测要点(对着真实文章页定):
- 标题/摘要/作者走 ``og:`` meta(最稳),公众号名走 ``var nickname = htmlDecode("...")``,
  发布时刻走 ``var ct = "<epoch>"``;正文在 ``id="js_content"`` 区,以 ``content_bottom_area``
  / ``js_temp_bottom_area`` 为收尾哨兵。
- 微信文章页常触发 ``http.client.IncompleteRead``(声明的 Content-Length 收不齐)→ 用
  ``e.partial`` 兜住(已读到的就是完整正文)。
- 数据中心 IP 偶尔被返「环境异常」验证页 → 解析不到标题且正文为空时,按失败优雅降级。
"""
from __future__ import annotations

import html
import http.client
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memomate-wechat-mp")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"<(?:p|div|section|br|h[1-6]|li|tr|blockquote)\b[^>]*>", re.IGNORECASE)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


class _RateLimiter:
    """Minimal min-interval limiter(与 zhihu/bilibili/weather/github/hn 同款)。"""

    def __init__(self, min_interval: float = 1.0) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait_seconds(self, now: float) -> float:
        return max(0.0, self.min_interval - (now - self._last))

    def acquire(self) -> None:
        wait = self.wait_seconds(time.monotonic())
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()


_limiter = _RateLimiter(1.0)


# ============ 纯函数(离线可单测) ============
def is_wechat_article_url(url: str) -> bool:
    """是否合法的微信文章链接。**也是 SSRF 边界**:必须严格校验 host==mp.weixin.qq.com,
    不能用子串匹配——否则 http://169.254.169.254/mp.weixin.qq.com/s 之类会绕过去抓内网。"""
    try:
        p = urllib.parse.urlparse((url or "").strip())
    except ValueError:
        return False
    return (
        p.scheme in ("http", "https")
        and p.hostname == "mp.weixin.qq.com"
        and (p.path == "/s" or p.path.startswith("/s/"))
    )


def _meta(html_text: str, prop: str) -> str:
    m = re.search(rf'<meta\s+property="{re.escape(prop)}"\s+content="([^"]*)"', html_text)
    return html.unescape(m.group(1)).strip() if m else ""


def _first(html_text: str, pattern: str) -> str:
    m = re.search(pattern, html_text)
    return html.unescape(m.group(1)).strip() if m else ""


def _html_to_text(fragment: str) -> str:
    """正文 HTML 片段 → 可读纯文本:去脚本/样式、块级标签转换行、去残留标签、解实体、压空白。"""
    s = _SCRIPT_STYLE_RE.sub(" ", fragment or "")
    s = _BLOCK_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t ​]+", " ", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _extract_body(html_text: str) -> str:
    """抽 id="js_content" 区正文 → 纯文本。定位失败返回空串。"""
    m = re.search(r'id="js_content"[^>]*>', html_text)
    if not m:
        return ""
    rest = html_text[m.end():]
    end = re.search(r'<div[^>]*id="(?:content_bottom_area|js_temp_bottom_area)"', rest)
    return _html_to_text(rest[: end.start()] if end else rest)


def _format_publish_time(ct: str | None) -> str:
    """微信 ct(发布时刻 Unix 秒)→ 北京时间 'YYYY-MM-DD HH:MM'。非法返回空串。"""
    if not ct or not str(ct).isdigit():
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(int(ct) + 8 * 3600))


def _publish_epoch(html_text: str) -> str:
    """发布时刻 Unix 秒。优先取**正文之前**就出现的早期来源(抗 IncompleteRead 截断),
    回退到文末 ``var ct``(整页读全时才在)。"""
    m = re.search(r"(?:create_timestamp|ori_create_time)\s*:\s*'(\d+)'", html_text)
    if not m:
        m = re.search(r'var ct\s*=\s*"(\d+)"', html_text)
    return m.group(1) if m else ""


def parse_article(html_text: str, url: str = "") -> dict:
    """从文章页 HTML 抽结构化字段(纯函数,不联网)。

    抗截断设计:微信文章页 3MB+ 且常 IncompleteRead 截断尾部,而 ``var nickname`` /
    ``var ct`` / ``var user_name`` 在文末。故 account 在 nickname 缺失时回退到 ``author``
    (og 头部,必在),publish_time 优先用正文前的 ``create_timestamp``。account_id 仅文末有,
    属 best-effort,截断时可能为空。
    """
    title = _meta(html_text, "og:title") or _first(
        html_text, r'id="activity-name"[^>]*>\s*([^<]+?)\s*<'
    )
    author = _meta(html_text, "og:article:author")
    account = _first(
        html_text, r'var nickname\s*=\s*(?:htmlDecode\(\s*)?["\']([^"\']*)["\']'
    ) or author
    body = _extract_body(html_text)
    ok = bool(title) or bool(body)
    return {
        "url": url,
        "title": title,
        "account": account,
        "account_id": _first(html_text, r'var user_name\s*=\s*"([^"]*)"'),
        "author": author,
        "digest": _meta(html_text, "og:description"),
        "publish_time": _format_publish_time(_publish_epoch(html_text)),
        "text": body,
        "error": None if ok else "解析失败(可能是验证页/链接失效)",
    }


def _error(url: str, msg: str) -> dict:
    return {"url": url, "title": "", "account": "", "account_id": "", "author": "",
            "digest": "", "publish_time": "", "text": "", "error": msg}


# ============ 网络(优雅降级) ============
def _fetch_html(url: str, timeout: float = 20.0) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                raw = resp.read()
            except http.client.IncompleteRead as e:
                raw = e.partial  # 微信常收不齐 Content-Length,已读部分即完整正文
            return raw.decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return None


# ============ tool ============
@mcp.tool()
def fetch_wechat_article(url: str) -> dict:
    """抓取并解析一篇公开的微信公众号文章。

    Args:
        url: 公众号文章链接(``https://mp.weixin.qq.com/s/...`` 或 ``/s?__biz=...``)。

    Returns:
        统一形状 dict:``url / title / account / account_id / author / digest /
        publish_time / text / error``。非文章链接、网络失败或解析失败时 ``error`` 非空、
        其余字段为空(优雅降级,不抛给 MCP client)。
    """
    if not is_wechat_article_url(url):
        return _error(url, "不是有效的微信公众号文章链接(应为 mp.weixin.qq.com/s/...)")

    _limiter.acquire()
    html_text = _fetch_html(url.strip())
    if html_text is None:
        return _error(url, "抓取失败(网络错误)")
    return parse_article(html_text, url=url.strip())


def main() -> None:
    """Entry point for the WeChat MP MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
