"""MCP server for Hacker News (official Firebase API + Algolia search, no key).

Hacker News 有官方只读 JSON API(Firebase),零鉴权:
  - 榜单 ID 列表:``/v0/{category}stories.json`` → ``[id, id, ...]``
  - 单条:``/v0/item/{id}.json`` → ``{id,title,url,score,by,descendants,time,...}``
全文检索走 Algolia 提供的 ``https://hn.algolia.com/api/v1/search``(同样免 key)。

约定与同仓其它 server 一致:仅标准库(``urllib`` / ``json``)、自我限流
(``_RateLimiter``)、纯解析/归一函数(离线可单测)、优雅降级(网络/解析错误返回 ``[]``
而非抛给 MCP client)。榜单接口是「取 ID 列表 → 逐条取详情」,单条详情失败只跳过该条,
不让整个榜单因一条坏数据崩掉。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

from runtime import run_server

mcp = FastMCP("memomate-hackernews")

_UA = "memomate-hackernews/0.1 (+https://github.com/Mrduan-cloud)"
_FIREBASE = "https://hacker-news.firebaseio.com/v0"
_ALGOLIA = "https://hn.algolia.com/api/v1/search"
_HN_ITEM = "https://news.ycombinator.com/item?id="

# 榜单分类(对应 {category}stories.json)+ 中文/常见别名归一
_ALLOWED_CATEGORY = {"top", "new", "best", "ask", "show", "job"}
_CATEGORY_ALIASES = {
    "hot": "top", "front": "top", "frontpage": "top", "热门": "top", "首页": "top",
    "newest": "new", "latest": "new", "最新": "new",
    "best": "best", "最佳": "best",
    "askhn": "ask", "ask_hn": "ask", "提问": "ask",
    "showhn": "show", "show_hn": "show", "展示": "show",
    "jobs": "job", "招聘": "job", "工作": "job",
}


class _RateLimiter:
    """Minimal min-interval limiter(与 zhihu/bilibili/weather/github_trending 同款)。

    只在每次「工具调用」入口 acquire 一次,不在逐条详情之间限流——HN API 本就为高并发
    只读设计,逐条之间再 sleep 只会让一次榜单拉取慢上十几秒。
    """

    def __init__(self, min_interval: float = 0.5) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait_seconds(self, now: float) -> float:
        return max(0.0, self.min_interval - (now - self._last))

    def acquire(self) -> None:
        wait = self.wait_seconds(time.monotonic())
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()


_limiter = _RateLimiter(0.5)


# ============ 纯函数(离线可单测) ============
def _normalize_category(category: str) -> str:
    c = (category or "").strip().lower().replace(" ", "").replace("-", "")
    if c in _ALLOWED_CATEGORY:
        return c
    return _CATEGORY_ALIASES.get(c, "top")


def _stories_endpoint(category: str) -> str:
    """榜单 ID 列表 URL。HN 端点是 topstories/newstories/beststories/askstories/...。"""
    return f"{_FIREBASE}/{_normalize_category(category)}stories.json"


def _item_endpoint(item_id: int) -> str:
    return f"{_FIREBASE}/item/{int(item_id)}.json"


def _search_url(query: str, limit: int) -> str:
    qs = urllib.parse.urlencode(
        {"query": query or "", "tags": "story", "hitsPerPage": max(1, min(int(limit), 50))}
    )
    return f"{_ALGOLIA}?{qs}"


def _humanize_age(seconds: float | None) -> str | None:
    """epoch 差值 → 人类可读年龄(m/h/d)。None / 负值 → None。"""
    if seconds is None or seconds < 0:
        return None
    s = int(seconds)
    if s < 3600:
        return f"{max(1, s // 60)}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _normalize_item(raw: dict | None, now_epoch: float) -> dict | None:
    """Firebase item dict → 统一输出。无 id/title(被删/dead/job 无标题)即返回 None。"""
    if not isinstance(raw, dict):
        return None
    item_id = raw.get("id")
    title = raw.get("title")
    if item_id is None or not title:
        return None
    created = raw.get("time")
    return {
        "id": item_id,
        "title": title,
        # Ask/Show/讨论帖常无外链,回退到 HN 讨论页,保证 url 一定可点
        "url": raw.get("url") or f"{_HN_ITEM}{item_id}",
        "score": raw.get("score"),
        "by": raw.get("by"),
        "comments": raw.get("descendants", 0),
        "age": _humanize_age((now_epoch - created) if created else None),
        "hn_url": f"{_HN_ITEM}{item_id}",
    }


def _parse_search(payload: dict | None, limit: int) -> list[dict]:
    """Algolia 搜索响应 → 与榜单同形状的列表。"""
    if not isinstance(payload, dict):
        return []
    out: list[dict] = []
    for hit in payload.get("hits", []):
        if not isinstance(hit, dict):
            continue
        obj_id = hit.get("objectID")
        title = hit.get("title") or hit.get("story_title")
        if obj_id is None or not title:
            continue
        out.append({
            "id": _to_int(obj_id),
            "title": title,
            "url": hit.get("url") or f"{_HN_ITEM}{obj_id}",
            "score": hit.get("points"),
            "by": hit.get("author"),
            "comments": hit.get("num_comments", 0),
            "age": None,  # 搜索结果按相关度排序,年龄意义不大,留空
            "hn_url": f"{_HN_ITEM}{obj_id}",
        })
        if len(out) >= limit:
            break
    return out


def _to_int(s: object) -> int | None:
    try:
        return int(str(s).strip())
    except (ValueError, TypeError):
        return None


# ============ 网络(优雅降级) ============
def _fetch_json(url: str, timeout: float = 15.0) -> object | None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


# ============ tools ============
@mcp.tool()
def get_hackernews_stories(category: str = "top", limit: int = 15) -> list[dict]:
    """获取 Hacker News 榜单(官方 Firebase API,零鉴权)。

    Args:
        category: 榜单分类 top / new / best / ask / show / job(也认 热门/最新/最佳/提问/展示/招聘);默认 top。
        limit: 返回数量,clamp 到 1..30(逐条取详情,过大请求数会变多)。

    Returns:
        条目列表,每项含 id / title / url(无外链时为 HN 讨论页)/ score / by /
        comments(评论数)/ age(年龄 m/h/d)/ hn_url。网络或解析失败返回**空列表**
        (优雅降级);个别条目坏掉只跳过该条。
    """
    category = _normalize_category(category)
    limit = max(1, min(int(limit), 30))

    _limiter.acquire()
    ids = _fetch_json(_stories_endpoint(category))
    if not isinstance(ids, list):
        return []

    now_epoch = time.time()
    out: list[dict] = []
    for item_id in ids[:limit]:
        item = _normalize_item(_fetch_json(_item_endpoint(item_id)), now_epoch)
        if item:
            out.append(item)
    return out


@mcp.tool()
def search_hackernews(query: str, limit: int = 15) -> list[dict]:
    """全文检索 Hacker News 帖子(Algolia API,零鉴权)。

    Args:
        query: 检索关键词。
        limit: 返回数量,clamp 到 1..50;默认 15。

    Returns:
        与榜单同形状的条目列表(age 留空,按相关度排序)。网络/解析失败返回空列表。
    """
    if not (query or "").strip():
        return []
    limit = max(1, min(int(limit), 50))

    _limiter.acquire()
    payload = _fetch_json(_search_url(query, limit))
    return _parse_search(payload, limit)


def main() -> None:
    """Entry point for the Hacker News MCP server (stdio by default; --transport streamable-http for remote access)."""
    run_server(mcp)


if __name__ == "__main__":
    main()
