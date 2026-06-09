"""MCP server for searching B站 videos via the public web search API.

Zero external dependencies: uses only the Python standard library for HTTP
and JSON. The search endpoint does not require authentication, but B站's
anti-bot guard expects a realistic User-Agent and a `buvid3` cookie that
we obtain by hitting the homepage first.

Subtitles are different: B站 only returns subtitle URLs to **logged-in**
clients, so ``get_video_subtitles`` reads a ``SESSDATA`` cookie from the
``BILIBILI_SESSDATA`` environment variable (never hard-coded / committed) and
injects it into the cookie jar. Without it the subtitle list comes back empty.
"""

from __future__ import annotations

import contextlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import Cookie, CookieJar
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memomate-bilibili-search")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
_HOME = "https://www.bilibili.com"
# Legacy non-wbi search endpoint: works with just buvid3 cookie + UA, no signing.
# The newer /wbi/search/all/v2 endpoint requires w_rid / wts query signing,
# which adds complexity for no benefit — this one returns the same data.
_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
_VIDEO_INFO_API = "https://api.bilibili.com/x/web-interface/view"
# Non-wbi player endpoint: returns subtitle metadata when authenticated (SESSDATA),
# again sidestepping the wbi query-signing the /wbi/v2 variant would require.
_PLAYER_API = "https://api.bilibili.com/x/player/v2"
_TAG_RE = re.compile(r"<[^>]+>")
_BVID_RE = re.compile(r"(BV[0-9A-Za-z]{10})")
_SESSDATA_ENV = "BILIBILI_SESSDATA"


class _RateLimiter:
    """Minimal min-interval limiter (same shape as the 知乎 server's).

    ``wait_seconds(now)`` is a **pure** function of the last-call timestamp so the
    throttle math is unit-testable without sleeping; ``acquire()`` applies it
    against the real monotonic clock. Subtitle extraction makes 3 sequential
    calls (view → player → CDN), so self-throttling keeps us polite.
    """

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


def _sessdata() -> str | None:
    """Read the SESSDATA cookie from the environment (never hard-coded).

    Returns ``None`` when unset/blank so callers can degrade gracefully.
    """
    return (os.environ.get(_SESSDATA_ENV) or "").strip() or None


def _make_sessdata_cookie(value: str) -> Cookie:
    """Build a ``.bilibili.com`` SESSDATA cookie for injection into a jar."""
    return Cookie(
        version=0, name="SESSDATA", value=value,
        port=None, port_specified=False,
        domain=".bilibili.com", domain_specified=True, domain_initial_dot=True,
        path="/", path_specified=True,
        secure=True, expires=None, discard=False,
        comment=None, comment_url=None, rest={"HttpOnly": None},
    )


def _new_opener(sessdata: str | None = None) -> urllib.request.OpenerDirector:
    """Build an opener with a cookie jar and pre-warmed buvid3 cookie.

    If ``sessdata`` is given it is injected as a login cookie *before* warmup,
    enabling endpoints (like subtitles) that require authentication.
    """
    jar = CookieJar()
    if sessdata:
        jar.set_cookie(_make_sessdata_cookie(sessdata))
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", _UA),
        ("Referer", _HOME + "/"),
        ("Accept", "application/json, text/plain, */*"),
        ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),
    ]
    # Warm up cookies by hitting the homepage once. Even if warmup fails the
    # search endpoint usually still works, just with reduced reliability.
    with contextlib.suppress(Exception):
        opener.open(_HOME, timeout=15).read(1024)
    return opener


def _strip_html(s: str) -> str:
    """Remove <em class='keyword'> tags and decode entities from a B站 title."""
    return html.unescape(_TAG_RE.sub("", s))


def _extract_bvid(s: str) -> str:
    """Extract a bare BV id from an id or a full URL. Raises if none found."""
    m = _BVID_RE.search(str(s))
    if not m:
        raise ValueError(f"Could not extract BV id from: {s!r}")
    return m.group(1)


def _normalize_url(u: str) -> str:
    """Prefix protocol-relative URLs (B站 returns ``//i0.hdslb.com/...``)."""
    u = u or ""
    return "https:" + u if u.startswith("//") else u


def _get_json(opener: urllib.request.OpenerDirector, url: str) -> dict[str, Any]:
    req = urllib.request.Request(url)
    with opener.open(req, timeout=20) as resp:
        payload = resp.read().decode("utf-8")
    data = json.loads(payload)
    if data.get("code") != 0:
        raise RuntimeError(f"B站 API error code={data.get('code')} message={data.get('message')}")
    return data


@mcp.tool()
def search_bilibili_videos(
    query: str,
    page: int = 1,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search B站 videos by keyword.

    Args:
        query: Search keyword. Chinese or English both work.
        page: 1-indexed result page (B站 returns ~20 results per page).
        limit: Max number of videos to return from the requested page
               (clamped to 1..30).

    Returns:
        List of videos with bvid, title, uploader, duration, view count,
        publish date, description, and web url.
    """
    page = max(1, int(page))
    limit = max(1, min(int(limit), 30))

    params = {
        "keyword": query,
        "search_type": "video",
        "page": str(page),
        "page_size": "20",
    }
    url = f"{_SEARCH_API}?{urllib.parse.urlencode(params)}"

    opener = _new_opener()
    data = _get_json(opener, url)

    # Legacy /search/type endpoint returns videos directly under data.result
    videos = data.get("data", {}).get("result") or []

    out: list[dict[str, Any]] = []
    for v in videos[:limit]:
        bvid = v.get("bvid") or ""
        out.append(
            {
                "bvid": bvid,
                "title": _strip_html(v.get("title") or ""),
                "uploader": v.get("author") or "",
                "uploader_mid": v.get("mid"),
                "duration": v.get("duration") or "",  # already "MM:SS"
                "view_count": v.get("play"),
                "danmaku_count": v.get("video_review"),
                "publish_ts": v.get("pubdate"),
                "description": _strip_html(v.get("description") or ""),
                "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
                "thumbnail": ("https:" + v["pic"]) if v.get("pic", "").startswith("//") else v.get("pic"),
            }
        )
    return out


@mcp.tool()
def get_video_info(bvid: str) -> dict[str, Any]:
    """Fetch detailed info for one B站 video by its BV id.

    Args:
        bvid: B站 video id, e.g. "BV1xx411c7mD". Either bare or as part of
              a URL is accepted.
    """
    bvid = _extract_bvid(bvid)

    opener = _new_opener()
    data = _get_json(opener, f"{_VIDEO_INFO_API}?bvid={bvid}")
    v = data.get("data", {})
    owner = v.get("owner") or {}
    stat = v.get("stat") or {}

    return {
        "bvid": v.get("bvid"),
        "aid": v.get("aid"),
        "title": v.get("title") or "",
        "description": v.get("desc") or "",
        "duration_seconds": v.get("duration"),
        "publish_ts": v.get("pubdate"),
        "uploader": owner.get("name") or "",
        "uploader_mid": owner.get("mid"),
        "view_count": stat.get("view"),
        "like_count": stat.get("like"),
        "coin_count": stat.get("coin"),
        "favorite_count": stat.get("favorite"),
        "share_count": stat.get("share"),
        "danmaku_count": stat.get("danmaku"),
        "url": f"https://www.bilibili.com/video/{v.get('bvid')}",
        "thumbnail": v.get("pic"),
    }


# ============ subtitles ============
def _extract_aid_cid(view_payload: dict[str, Any], part: int = 1) -> tuple[int, int]:
    """Pull (aid, cid) for a given 1-indexed ``part`` out of a /view payload.

    Multi-part videos expose a ``pages[]`` array (each with its own ``cid``);
    single-part videos carry ``cid`` at the top level. ``part`` is clamped into
    range. Raises ``ValueError`` if aid/cid can't be resolved.
    """
    data = view_payload.get("data") or {}
    aid = data.get("aid")
    pages = data.get("pages") or []
    if pages:
        idx = min(max(1, int(part)) - 1, len(pages) - 1)
        cid = (pages[idx] or {}).get("cid")
    else:
        cid = data.get("cid")
    if not aid or not cid:
        raise ValueError("missing aid/cid in view payload")
    return int(aid), int(cid)


def _player_api_url(aid: int, cid: int) -> str:
    """Build the player/v2 URL carrying subtitle metadata. Pure (no I/O)."""
    return f"{_PLAYER_API}?{urllib.parse.urlencode({'aid': aid, 'cid': cid})}"


def _parse_subtitle_list(player_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize ``data.subtitle.subtitles[]`` from a player/v2 payload.

    AI-generated tracks use a ``ai-*`` language code (e.g. ``ai-zh``); we flag
    those so callers can prefer human subtitles. URLs are made absolute.
    """
    subs = (((player_payload.get("data") or {}).get("subtitle") or {}).get("subtitles")) or []
    out: list[dict[str, Any]] = []
    for s in subs:
        lan = s.get("lan") or ""
        out.append(
            {
                "lan": lan,
                "lan_doc": s.get("lan_doc") or "",
                "url": _normalize_url(s.get("subtitle_url") or ""),
                "is_ai": lan.startswith("ai-") or bool(s.get("ai_status")),
            }
        )
    return out


def _pick_subtitle(
    subs: list[dict[str, Any]], lang: str | None = None
) -> dict[str, Any] | None:
    """Choose a subtitle track. Pure.

    Preference: exact ``lang`` match → prefix match (``zh`` ↔ ``zh-CN``) →
    first human (non-AI) track → first track. ``None`` if the list is empty.
    """
    if not subs:
        return None
    if lang:
        for s in subs:
            if s["lan"] == lang:
                return s
        for s in subs:
            if s["lan"].startswith(lang) or lang.startswith(s["lan"]):
                return s
    human = [s for s in subs if not s["is_ai"]]
    return (human or subs)[0]


def _parse_subtitle_body(subtitle_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a downloaded subtitle file (``{"body": [{from,to,content}]}``)."""
    out: list[dict[str, Any]] = []
    for seg in subtitle_json.get("body") or []:
        out.append(
            {
                "from": seg.get("from"),
                "to": seg.get("to"),
                "content": (seg.get("content") or "").strip(),
            }
        )
    return out


def _segments_to_text(segments: list[dict[str, Any]]) -> str:
    """Join subtitle segments into a plain-text transcript (one line each)."""
    return "\n".join(s["content"] for s in segments if s.get("content"))


@mcp.tool()
def get_video_subtitles(
    bvid: str,
    lang: str | None = None,
    part: int = 1,
) -> dict[str, Any]:
    """Fetch a B站 video's subtitles as timed segments + a plain-text transcript.

    Requires the ``BILIBILI_SESSDATA`` environment variable (a logged-in
    SESSDATA cookie) — B站 only returns subtitle URLs to authenticated clients.
    The cookie is read from the env at call time and never logged or persisted.

    Args:
        bvid: B站 video id or URL (the BV id is extracted).
        lang: Preferred language code, e.g. "zh-CN" / "en" / "ai-zh". If omitted
              or not found, prefers a human track, else the first available.
        part: 1-indexed part for multi-part videos (clamped to range).

    Returns:
        On success: dict with ``lang``, ``is_ai``, ``available_langs``,
        ``segment_count``, ``segments`` (each {from,to,content}), ``text``.
        On failure / no subtitles: a dict with an ``error`` key (never raises to
        the MCP client), including ``available_langs`` to aid debugging.
    """
    bvid = _extract_bvid(bvid)
    sessdata = _sessdata()
    opener = _new_opener(sessdata)
    net_errors = (urllib.error.URLError, json.JSONDecodeError, OSError, RuntimeError)

    # 1) resolve aid + cid from the view API
    _limiter.acquire()
    try:
        view = _get_json(opener, f"{_VIDEO_INFO_API}?bvid={bvid}")
        aid, cid = _extract_aid_cid(view, part)
    except net_errors:
        return {"bvid": bvid, "error": "failed to fetch video info"}
    except ValueError:
        return {"bvid": bvid, "error": "could not resolve aid/cid for this video"}

    # 2) fetch subtitle metadata from the player API
    _limiter.acquire()
    try:
        player = _get_json(opener, _player_api_url(aid, cid))
    except net_errors:
        return {"bvid": bvid, "aid": aid, "cid": cid,
                "error": "failed to fetch subtitle metadata"}

    subs = _parse_subtitle_list(player)
    chosen = _pick_subtitle(subs, lang)
    if not chosen or not chosen["url"]:
        hint = (
            "no subtitles available — the video may have none, or "
            f"{_SESSDATA_ENV} is unset/invalid (subtitle URLs require login)"
            if not sessdata or not subs
            else "no subtitle track matched the requested language"
        )
        return {
            "bvid": bvid, "aid": aid, "cid": cid,
            "available_langs": [s["lan"] for s in subs],
            "authenticated": bool(sessdata),
            "error": hint,
        }

    # 3) download + parse the subtitle file itself (raw CDN JSON, not code-wrapped)
    _limiter.acquire()
    try:
        with opener.open(urllib.request.Request(chosen["url"]), timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return {"bvid": bvid, "aid": aid, "cid": cid,
                "error": "failed to download subtitle file"}

    segments = _parse_subtitle_body(body)
    return {
        "bvid": bvid,
        "aid": aid,
        "cid": cid,
        "lang": chosen["lan"],
        "lang_doc": chosen["lan_doc"],
        "is_ai": chosen["is_ai"],
        "available_langs": [s["lan"] for s in subs],
        "segment_count": len(segments),
        "segments": segments,
        "text": _segments_to_text(segments),
        "url": f"https://www.bilibili.com/video/{bvid}",
    }


def main() -> None:
    """Entry point for the B站 search MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
