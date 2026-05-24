"""MCP server for searching B站 videos via the public web search API.

Zero external dependencies: uses only the Python standard library for HTTP
and JSON. The search endpoint does not require authentication, but B站's
anti-bot guard expects a realistic User-Agent and a `buvid3` cookie that
we obtain by hitting the homepage first.
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
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
_TAG_RE = re.compile(r"<[^>]+>")


def _new_opener() -> urllib.request.OpenerDirector:
    """Build an opener with a cookie jar and pre-warmed buvid3 cookie."""
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", _UA),
        ("Referer", _HOME + "/"),
        ("Accept", "application/json, text/plain, */*"),
        ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),
    ]
    # Warm up cookies by hitting the homepage once.
    try:
        opener.open(_HOME, timeout=15).read(1024)
    except Exception:
        # Even if warmup fails the search endpoint usually still works,
        # just with reduced reliability. Continue anyway.
        pass
    return opener


def _strip_html(s: str) -> str:
    """Remove <em class='keyword'> tags and decode entities from a B站 title."""
    return html.unescape(_TAG_RE.sub("", s))


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
    # Accept full URLs by extracting the BV id.
    m = re.search(r"(BV[0-9A-Za-z]{10})", bvid)
    if not m:
        raise ValueError(f"Could not extract BV id from: {bvid!r}")
    bvid = m.group(1)

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


def main() -> None:
    """Entry point for the B站 search MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
