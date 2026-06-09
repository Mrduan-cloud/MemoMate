# bilibili_search

MCP server for searching B站 videos via the public web search API.

**Zero external dependencies** — uses only the Python standard library (`urllib`, `http.cookiejar`, `json`).

## Tools

| Tool | Description |
|---|---|
| `search_bilibili_videos(query, page=1, limit=10)` | Search B站 videos by keyword. Returns bvid, title, uploader, duration, view count, publish date, description, url, thumbnail. |
| `get_video_info(bvid)` | Fetch detailed info for one video by BV id (also accepts a full B站 URL). Returns title, description, duration, uploader, view/like/coin/favorite/share/danmaku counts. |
| `get_video_subtitles(bvid, lang=None, part=1)` | Fetch a video's subtitles as timed segments (`{from,to,content}`) plus a plain-text transcript. Prefers a human track over AI-generated; `lang` picks a specific track (e.g. `zh-CN`, `en`, `ai-zh`). **Requires `BILIBILI_SESSDATA`** (see below). |

## How it works

The B站 search endpoint (`api.bilibili.com/x/web-interface/wbi/search/all/v2`) is **publicly accessible without login**, but the anti-bot guard expects:

1. A realistic browser **User-Agent**.
2. A **`buvid3` cookie** that B站 sets on first visit to the homepage.

This server uses a stdlib `CookieJar` and warms the cookie by hitting the homepage once per process. Search and video info need **no login**.

### Subtitles need login (`BILIBILI_SESSDATA`)

B站 only returns subtitle URLs to **authenticated** clients, so `get_video_subtitles` reads a logged-in `SESSDATA` cookie from the **`BILIBILI_SESSDATA` environment variable** and injects it into the cookie jar. The value is read at call time and **never logged, persisted, or committed** — keep it in your shell/MCP env, not in code.

```bash
# get SESSDATA from your browser dev-tools (Application → Cookies → bilibili.com)
export BILIBILI_SESSDATA="xxxxxxxx"
```

Without it (or with an expired cookie) the subtitle list comes back empty and the tool returns a graceful `{"error": ...}` dict (it never raises). The flow is 3 sequential calls — `view` (resolve aid/cid) → `player/v2` (subtitle metadata) → CDN subtitle JSON — self-throttled to ≥1s between calls.

## Example prompts

After registering with Claude Code (see below), try:

- *"Search B站 for videos about LangGraph tutorials."*
- *"用 memomate-bilibili 找一下 RAG 入门视频，给我前 5 个。"*
- *"Get the view count and upload date for BV1xx411c7mD."*

## Plug into Claude Code

```bash
claude mcp add memomate-bilibili --scope user \
  -- uv run --directory D:/project/MemoMate memomate-bilibili
```

## Limitations

- The search endpoint is rate-limited by IP. Hammering it will eventually return code `-412` (anti-crawl). The server self-throttles subtitle calls to ≥1s; add a similar pause around search in tight loops.
- `get_video_subtitles` depends on `BILIBILI_SESSDATA`; many videos also simply have no subtitle track, in which case `available_langs` is empty.
- Some queries (especially very generic keywords) may return zero `video` results because B站 prioritizes user/article results in the all/v2 endpoint. Try a more specific query.
