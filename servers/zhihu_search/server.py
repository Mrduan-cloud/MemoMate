"""MCP server for searching 知乎 questions/answers via the public web API.

Zero external dependencies: stdlib HTTP + JSON only. 知乎 has aggressive
anti-scraping, so this server:

1. sends a realistic browser User-Agent and warms a cookie jar off the homepage
   (the ``search_v3`` endpoint expects a few cookies set on first visit);
2. **self-rate-limits** to >= 2s between calls (``_RateLimiter``) — 知乎 throttles
   hard, so we throttle ourselves first (this is the "rate-limit 占位" the
   scaffold called for; can later grow into a token bucket / persistent window);
3. degrades gracefully — any network / parse error returns ``[]`` (or an error
   dict for ``fetch_answer``) rather than raising to the MCP client.
"""

from __future__ import annotations

import contextlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memomate-zhihu-search")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
_HOME = "https://www.zhihu.com"
_SEARCH_API = "https://www.zhihu.com/api/v4/search_v3"
_ANSWER_API = "https://www.zhihu.com/api/v4/answers"
_TAG_RE = re.compile(r"<[^>]+>")

# 知乎 search_v3 returns mixed object types; we filter client-side to the
# requested kind. Only these two are user-facing for now.
_ALLOWED_KINDS = {"question", "answer"}


class _RateLimiter:
    """Minimal min-interval limiter.

    ``wait_seconds(now)`` is a **pure** function of the last-call timestamp, so
    the throttle math is unit-testable without sleeping; ``acquire()`` applies it
    against the real monotonic clock.
    """

    def __init__(self, min_interval: float = 2.0) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait_seconds(self, now: float) -> float:
        return max(0.0, self.min_interval - (now - self._last))

    def acquire(self) -> None:
        wait = self.wait_seconds(time.monotonic())
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()


_limiter = _RateLimiter(2.0)


def _new_opener() -> urllib.request.OpenerDirector:
    """Opener with a cookie jar pre-warmed by one homepage hit."""
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", _UA),
        ("Referer", _HOME + "/"),
        ("Accept", "application/json, text/plain, */*"),
        ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),
        ("x-requested-with", "fetch"),
    ]
    # Warmup failure isn't fatal — the search endpoint may still answer,
    # just less reliably.
    with contextlib.suppress(Exception):
        opener.open(_HOME, timeout=15).read(1024)
    return opener


def _normalize_kind(kind: str) -> str:
    """Clamp the requested kind to a supported value (default 'question')."""
    k = (kind or "").strip().lower()
    return k if k in _ALLOWED_KINDS else "question"


def _build_search_url(query: str, limit: int) -> str:
    """Build the 知乎 ``search_v3`` query URL.

    Pure (no I/O) so query construction is unit-testable offline. ``kind`` is
    NOT part of the URL — ``search_v3`` (``t=general``) returns mixed object
    types and we filter to the requested kind in ``_parse_search``.
    """
    params = {
        "t": "general",
        "q": query,
        "correction": "1",
        "limit": str(limit),
        "offset": "0",
    }
    return f"{_SEARCH_API}?{urllib.parse.urlencode(params)}"


def _strip_html(s: str) -> str:
    """Drop tags (知乎 highlights matches in <em>) and decode HTML entities."""
    return html.unescape(_TAG_RE.sub("", s or "")).strip()


def _parse_search(payload: dict[str, Any], kind: str, limit: int) -> list[dict[str, Any]]:
    """Parse a ``search_v3`` JSON body into a list of normalized results.

    Filters to the requested ``kind`` (question / answer). Defensive: 知乎 wraps
    each hit as ``data[].object`` with a shifting shape and interleaves noise
    rows (``relevant_query`` / ``search_club`` …), so every field is a guarded
    ``.get()`` and unknown object types are skipped.
    """
    out: list[dict[str, Any]] = []
    for item in payload.get("data") or []:
        obj = item.get("object") or {}
        if obj.get("type") != kind:
            continue
        if kind == "question":
            qid = obj.get("id")
            out.append(
                {
                    "kind": "question",
                    "id": qid,
                    "title": _strip_html(obj.get("title") or obj.get("name") or ""),
                    "excerpt": _strip_html(obj.get("excerpt") or ""),
                    "answer_count": obj.get("answer_count"),
                    "url": f"https://www.zhihu.com/question/{qid}" if qid else "",
                }
            )
        else:  # answer
            aid = obj.get("id")
            question = obj.get("question") or {}
            qid = question.get("id")
            out.append(
                {
                    "kind": "answer",
                    "id": aid,
                    "question_title": _strip_html(question.get("title") or question.get("name") or ""),
                    "author": (obj.get("author") or {}).get("name") or "",
                    "excerpt": _strip_html(obj.get("excerpt") or ""),
                    "voteup_count": obj.get("voteup_count"),
                    "url": (
                        f"https://www.zhihu.com/question/{qid}/answer/{aid}" if qid and aid else ""
                    ),
                }
            )
        if len(out) >= limit:
            break
    return out


@mcp.tool()
def search_zhihu(query: str, kind: str = "question", limit: int = 5) -> list[dict[str, Any]]:
    """Search 知乎 questions or answers by keyword.

    Args:
        query: Search keyword (Chinese or English).
        kind: 'question' or 'answer' (default 'question'; anything else falls
              back to 'question').
        limit: Max number of results, clamped to 1..20.

    Returns:
        List of normalized results. Returns an **empty list** if 知乎 blocks the
        request (anti-bot / rate-limit) — the scaffold favors graceful
        degradation over raising to the MCP client.
    """
    kind = _normalize_kind(kind)
    limit = max(1, min(int(limit), 20))
    url = _build_search_url(query, limit)

    _limiter.acquire()
    opener = _new_opener()
    try:
        with opener.open(urllib.request.Request(url), timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return []
    return _parse_search(payload, kind, limit)


@mcp.tool()
def fetch_answer(answer_id: str) -> dict[str, Any]:
    """Fetch one 知乎 answer's body as plain text.

    Args:
        answer_id: Numeric answer id, or a full answer URL (the id is extracted).

    Returns:
        Dict with the answer body (``content_text``) and metadata, or a dict with
        an ``error`` key if 知乎 blocked the request.
    """
    m = re.search(r"(\d{6,})", str(answer_id))
    if not m:
        raise ValueError(f"Could not extract a 知乎 answer id from: {answer_id!r}")
    aid = m.group(1)

    params = {"include": "content,voteup_count,author,question"}
    url = f"{_ANSWER_API}/{aid}?{urllib.parse.urlencode(params)}"

    _limiter.acquire()
    opener = _new_opener()
    try:
        with opener.open(urllib.request.Request(url), timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return {"id": aid, "error": "fetch failed — 知乎 may have blocked the request"}

    question = data.get("question") or {}
    qid = question.get("id")
    return {
        "id": data.get("id") or aid,
        "question_title": _strip_html(question.get("title") or ""),
        "author": (data.get("author") or {}).get("name") or "",
        "voteup_count": data.get("voteup_count"),
        "content_text": _strip_html(data.get("content") or ""),
        "url": f"https://www.zhihu.com/question/{qid}/answer/{aid}" if qid else "",
    }


def main() -> None:
    """Entry point for the 知乎 search MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
