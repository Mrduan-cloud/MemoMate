"""MCP server for GitHub Trending repositories (scrape, no API key).

GitHub 没有官方 trending API,本 server 解析 https://github.com/trending 的 HTML
(``daily`` / ``weekly`` / ``monthly`` + 语言过滤)。零外部依赖:仅用标准库
``urllib`` / ``html`` / ``re``。

约定与同仓其它 server 一致:自我限流(``_RateLimiter``)、纯解析函数(离线可单测)、
优雅降级(网络/解析错误返回 ``[]`` 而非抛给 MCP client)。HTML 抓取天然脆弱,故每个
字段都用 guarded 正则,缺失即为 ``None``,不让整页解析因一个字段崩掉。
"""

from __future__ import annotations

import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

from runtime import run_server

mcp = FastMCP("memomate-github-trending")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
_BASE = "https://github.com/trending"
_TAG_RE = re.compile(r"<[^>]+>")

# since 取值(GitHub 仅这三档)+ 中文/常见别名归一
_ALLOWED_SINCE = {"daily", "weekly", "monthly"}
_SINCE_ALIASES = {
    "today": "daily", "day": "daily", "今日": "daily", "今天": "daily", "日": "daily",
    "week": "weekly", "本周": "weekly", "周": "weekly", "这周": "weekly",
    "month": "monthly", "本月": "monthly", "月": "monthly", "这个月": "monthly",
}
_PERIOD_WORD = {"daily": "today", "weekly": "this week", "monthly": "this month"}


class _RateLimiter:
    """Minimal min-interval limiter(与 zhihu/bilibili/weather 同款,wait_seconds 纯函数)。"""

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
def _normalize_since(since: str) -> str:
    s = (since or "").strip().lower()
    if s in _ALLOWED_SINCE:
        return s
    return _SINCE_ALIASES.get(s, "daily")


def _build_url(language: str, since: str) -> str:
    """Trending URL。语言作为路径段(URL 编码,如 c++ → c%2B%2B),since 作 query。"""
    since = _normalize_since(since)
    path = _BASE
    lang = (language or "").strip()
    if lang:
        path = f"{_BASE}/{urllib.parse.quote(lang, safe='')}"
    return f"{path}?since={since}"


def _strip_html(s: str) -> str:
    return html.unescape(_TAG_RE.sub("", s or "")).strip()


def _to_int(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(s.replace(",", "").strip())
    except ValueError:
        return None


def _split_rows(html_text: str) -> list[str]:
    """按 ``<article ... class="Box-row">`` 切分仓库行。"""
    parts = re.split(r'<article[^>]*class="Box-row"', html_text or "")
    return parts[1:]  # 第 0 段是表头之前的内容


def _parse_row(row: str, period_word: str) -> dict | None:
    """从单个 Box-row 片段抽取一个仓库。无法定位仓库名则返回 None。"""
    # 仓库名:优先 stargazers 链接(最稳),回退 h2 标题锚点
    m = re.search(r'href="/([^"/]+/[^"/]+)/stargazers"', row)
    if not m:
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', row)
    if not m:
        return None
    full_name = m.group(1).strip().rstrip("/")
    if full_name.count("/") != 1:
        return None

    desc_m = re.search(r'<p[^>]*class="col-9[^"]*"[^>]*>(.*?)</p>', row, re.DOTALL)
    lang_m = re.search(r'itemprop="programmingLanguage">\s*([^<]+?)\s*<', row)
    total_m = re.search(r'/stargazers"[^>]*>.*?([\d,]+)\s*</a>', row, re.DOTALL)
    fork_m = re.search(r'/(?:forks|network/members)"[^>]*>.*?([\d,]+)\s*</a>', row, re.DOTALL)
    period_m = re.search(rf'([\d,]+)\s+stars?\s+{re.escape(period_word)}', row)

    return {
        "full_name": full_name,
        "url": f"https://github.com/{full_name}",
        "description": _strip_html(desc_m.group(1)) if desc_m else "",
        "language": lang_m.group(1).strip() if lang_m else None,
        "stars": _to_int(total_m.group(1)) if total_m else None,
        "forks": _to_int(fork_m.group(1)) if fork_m else None,
        "stars_in_period": _to_int(period_m.group(1)) if period_m else None,
    }


def _parse_trending(html_text: str, since: str, limit: int) -> list[dict]:
    period_word = _PERIOD_WORD[_normalize_since(since)]
    out: list[dict] = []
    for row in _split_rows(html_text):
        repo = _parse_row(row, period_word)
        if repo:
            out.append(repo)
        if len(out) >= limit:
            break
    return out


# ============ tool ============
@mcp.tool()
def get_github_trending(language: str = "", since: str = "daily", limit: int = 15) -> list[dict]:
    """获取 GitHub Trending 热门仓库。

    Args:
        language: 编程语言过滤,如 "python" / "rust" / "c++"(留空=全部语言)。
        since: 时间范围 daily / weekly / monthly(也认 今日/本周/本月);默认 daily。
        limit: 返回数量,clamp 到 1..50。

    Returns:
        仓库列表,每项含 full_name / url / description / language / stars(总星) /
        forks / stars_in_period(该时段新增星)。GitHub 改版/反爬导致解析失败时返回
        **空列表**(优雅降级,不抛给 MCP client)。
    """
    since = _normalize_since(since)
    limit = max(1, min(int(limit), 50))
    url = _build_url(language, since)

    _limiter.acquire()
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html_text = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return []
    return _parse_trending(html_text, since, limit)


def main() -> None:
    """Entry point for the GitHub Trending MCP server (stdio by default; --transport streamable-http for remote access)."""
    run_server(mcp)


if __name__ == "__main__":
    main()
