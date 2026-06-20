"""MCP server for Stack Overflow (官方 Stack Exchange API, 免 key).

Stack Exchange 有官方只读 JSON API(``api.stackexchange.com/2.3``),匿名即可用
(无 key,每 IP 约 300 次/天配额):
  - 搜问题:``/search/advanced?q=...&tagged=...&site=stackoverflow`` → ``{items:[...]}``
  - 取答案:``/questions/{id}/answers?filter=withbody&site=stackoverflow`` → 带 ``body`` HTML

约定与同仓其它 server 一致:仅标准库(``urllib`` / ``json`` / ``re`` / ``html`` / ``gzip``)、
自我限流(``_RateLimiter``)、纯解析/归一函数(离线可单测)、优雅降级(网络/解析错误返回
``[]`` 而非抛给 MCP client)。答案正文是 HTML,用 stdlib 正则转可读纯文本(同 wechat_mp)。

实测要点(对着真实 SE API 响应定):
- 用 urllib(不发 ``Accept-Encoding``)时 SE 返回**未压缩** JSON;但官方文档声明「响应总是
  gzip」,故 ``_fetch_json`` 仍按魔数 ``\\x1f\\x8b`` 防御性解压,两种都吃得下。
- 问题无被采纳答案时 ``accepted_answer_id`` **字段缺失**(不是 null)→ 用其「是否存在」判
  ``accepted``;``is_answered`` 才是「有没有答案」的可靠信号。
- 答案对象不含 ``link`` 字段 → 用规范短链 ``stackoverflow.com/a/{answer_id}`` 构造。
"""

from __future__ import annotations

import gzip
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

from runtime import run_server

mcp = FastMCP("memomate-stackoverflow")

_UA = "memomate-stackoverflow/0.1 (+https://github.com/Mrduan-cloud)"
_API = "https://api.stackexchange.com/2.3"
_SITE = "stackoverflow"
_SO = "https://stackoverflow.com"

# search/advanced 支持的 sort + 中文/常见别名归一
_ALLOWED_SORT = {"relevance", "votes", "creation", "activity"}
_SORT_ALIASES = {
    "relevant": "relevance", "相关": "relevance", "相关度": "relevance",
    "score": "votes", "top": "votes", "hot": "votes", "赞": "votes", "热门": "votes", "高赞": "votes",
    "new": "creation", "newest": "creation", "latest": "creation", "最新": "creation",
    "active": "activity", "活跃": "activity",
}

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"<(?:p|div|section|br|h[1-6]|li|tr|pre|blockquote)\b[^>]*>", re.IGNORECASE)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_PRE_RE = re.compile(r"<pre\b[^>]*>(.*?)</pre>", re.IGNORECASE | re.DOTALL)
_PRE_PLACEHOLDER_RE = re.compile("\x00PRE(\\d+)\x00")


class _RateLimiter:
    """Minimal min-interval limiter(与 zhihu/bilibili/weather/github/hn 同款)。"""

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
def _normalize_sort(sort: str) -> str:
    s = (sort or "").strip().lower().replace(" ", "").replace("-", "")
    if s in _ALLOWED_SORT:
        return s
    return _SORT_ALIASES.get(s, "relevance")


def _search_url(query: str, tag: str, limit: int, sort: str) -> str:
    params = {
        "order": "desc",
        "sort": _normalize_sort(sort),
        "q": (query or "").strip(),
        "site": _SITE,
        "pagesize": max(1, min(int(limit), 30)),
        "filter": "default",
    }
    tag = (tag or "").strip()
    if tag:
        params["tagged"] = tag
    return f"{_API}/search/advanced?{urllib.parse.urlencode(params)}"


def _answers_url(question_id: int, limit: int) -> str:
    params = {
        "order": "desc",
        "sort": "votes",
        "site": _SITE,
        "pagesize": max(1, min(int(limit), 10)),
        "filter": "withbody",  # 默认不含正文,withbody 才带 body(HTML)
    }
    return f"{_API}/questions/{int(question_id)}/answers?{urllib.parse.urlencode(params)}"


def _humanize_age(seconds: float | None) -> str | None:
    """epoch 差值 → 人类可读年龄(m/h/d)。None / 负值 → None(与 hackernews 同款)。"""
    if seconds is None or seconds < 0:
        return None
    s = int(seconds)
    if s < 3600:
        return f"{max(1, s // 60)}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _strip_pre_inner(inner: str) -> str:
    """``<pre>`` 块内文本:去内层标签(如 ``<code>``)、解实体,但**保留缩进与换行**。

    代码答案靠行首缩进表意(Python/YAML 尤甚),故只 strip 首尾空行,绝不折叠行内空白。
    """
    return html.unescape(_TAG_RE.sub("", inner)).strip("\n")


def _html_to_text(fragment: str) -> str:
    """答案正文 HTML → 可读纯文本:去脚本/样式、块级标签转换行、去残留标签、解实体、压空白。

    关键:**先把 ``<pre>`` 代码块挖出来占位**,再对其余正文压空白——否则后面的
    ``[ \\t]+→空格`` / ``行首空白剥除`` 会把代码缩进吃光(SO 是代码站,缩进必须留)。
    占位符用 ``\\x00`` 哨兵(HTML 文本里不会出现),不会被标签正则/空白折叠误伤。
    """
    s = _SCRIPT_STYLE_RE.sub(" ", fragment or "")

    blocks: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        blocks.append(_strip_pre_inner(m.group(1)))
        return f"\n\x00PRE{len(blocks) - 1}\x00\n"

    s = _PRE_RE.sub(_stash, s)
    s = _BLOCK_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = s.strip()
    # 还原代码块(其缩进未经折叠)
    return _PRE_PLACEHOLDER_RE.sub(lambda m: blocks[int(m.group(1))], s)


def _normalize_question(raw: dict | None, now_epoch: float) -> dict | None:
    """SE question dict → 统一输出。无 question_id/title 即返回 None。"""
    if not isinstance(raw, dict):
        return None
    qid = raw.get("question_id")
    title = raw.get("title")
    if qid is None or not title:
        return None
    created = raw.get("creation_date")
    return {
        "id": qid,
        "title": html.unescape(title),  # SE title 含 &quot; 等实体
        "score": raw.get("score"),
        "answers": raw.get("answer_count", 0),
        "is_answered": bool(raw.get("is_answered")),
        # 无被采纳答案时该字段缺失(非 null),故用「是否存在」判定
        "accepted": raw.get("accepted_answer_id") is not None,
        "tags": raw.get("tags", []),
        "views": raw.get("view_count"),
        "age": _humanize_age((now_epoch - created) if created else None),
        "link": raw.get("link") or f"{_SO}/q/{qid}",
    }


def _normalize_answer(raw: dict | None, now_epoch: float) -> dict | None:
    """SE answer dict → 统一输出。无 answer_id 即返回 None。body(HTML)转纯文本。"""
    if not isinstance(raw, dict):
        return None
    aid = raw.get("answer_id")
    if aid is None:
        return None
    created = raw.get("creation_date")
    return {
        "id": aid,
        "score": raw.get("score"),
        "is_accepted": bool(raw.get("is_accepted")),
        "author": (raw.get("owner") or {}).get("display_name"),
        "body": _html_to_text(raw.get("body") or ""),
        "link": f"{_SO}/a/{aid}",  # 规范短链,302 跳到答案锚点
        "age": _humanize_age((now_epoch - created) if created else None),
    }


def _parse_items(payload: dict | None, limit: int, now_epoch: float, normalize) -> list[dict]:
    """SE 响应 ``{items:[...]}`` → 归一列表(search/answers 共用,只换 normalize 函数)。"""
    if not isinstance(payload, dict):
        return []
    out: list[dict] = []
    for raw in payload.get("items", []):
        item = normalize(raw, now_epoch)
        if item:
            out.append(item)
        if len(out) >= limit:
            break
    return out


# ============ 网络(优雅降级) ============
def _fetch_json(url: str, timeout: float = 15.0) -> object | None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if data[:2] == b"\x1f\x8b":  # gzip 魔数:官方文档称响应总是 gzip,防御性解压
            data = gzip.decompress(data)
        return json.loads(data.decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, EOFError):
        return None


# ============ tools ============
@mcp.tool()
def search_stackoverflow(query: str, tag: str = "", limit: int = 10, sort: str = "relevance") -> list[dict]:
    """搜索 Stack Overflow 问题(官方 Stack Exchange API,免 key)。

    Args:
        query: 检索关键词(标题/正文全文匹配)。
        tag: 可选标签过滤(如 ``python`` / ``rust``;多个用 ``;`` 分隔)。
        limit: 返回数量,clamp 到 1..30;默认 10。
        sort: 排序 relevance / votes / creation / activity(也认 相关/高赞/最新/活跃);默认 relevance。

    Returns:
        问题列表,每项含 id / title / score / answers(答案数)/ is_answered /
        accepted(是否有被采纳答案)/ tags / views / age(m/h/d)/ link。
        网络或解析失败返回**空列表**(优雅降级)。
    """
    if not (query or "").strip():
        return []
    limit = max(1, min(int(limit), 30))

    _limiter.acquire()
    payload = _fetch_json(_search_url(query, tag, limit, sort))
    return _parse_items(payload, limit, time.time(), _normalize_question)


@mcp.tool()
def get_stackoverflow_answers(question_id: int, limit: int = 3) -> list[dict]:
    """取某个 Stack Overflow 问题的答案正文(按得票降序,官方 API,免 key)。

    Args:
        question_id: 问题 id(``search_stackoverflow`` 返回项的 ``id``)。
        limit: 返回答案数,clamp 到 1..10;默认 3。

    Returns:
        答案列表,每项含 id / score / is_accepted / author / body(HTML 转纯文本)/
        link / age。网络或解析失败返回**空列表**(优雅降级)。
    """
    try:
        qid = int(question_id)
    except (ValueError, TypeError):
        return []
    if qid <= 0:
        return []
    limit = max(1, min(int(limit), 10))

    _limiter.acquire()
    payload = _fetch_json(_answers_url(qid, limit))
    return _parse_items(payload, limit, time.time(), _normalize_answer)


def main() -> None:
    """Entry point for the Stack Overflow MCP server (stdio by default; --transport streamable-http for remote access)."""
    run_server(mcp)


if __name__ == "__main__":
    main()
