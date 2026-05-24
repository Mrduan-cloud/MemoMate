# bilibili_search

MCP server for searching B站 videos via the public web search API.

**Zero external dependencies** — uses only the Python standard library (`urllib`, `http.cookiejar`, `json`).

## Tools

| Tool | Description |
|---|---|
| `search_bilibili_videos(query, page=1, limit=10)` | Search B站 videos by keyword. Returns bvid, title, uploader, duration, view count, publish date, description, url, thumbnail. |
| `get_video_info(bvid)` | Fetch detailed info for one video by BV id (also accepts a full B站 URL). Returns title, description, duration, uploader, view/like/coin/favorite/share/danmaku counts. |

## How it works

The B站 search endpoint (`api.bilibili.com/x/web-interface/wbi/search/all/v2`) is **publicly accessible without login**, but the anti-bot guard expects:

1. A realistic browser **User-Agent**.
2. A **`buvid3` cookie** that B站 sets on first visit to the homepage.

This server uses a stdlib `CookieJar` and warms the cookie by hitting the homepage once per process. No login or `SESSDATA` is required.

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

- The search endpoint is rate-limited by IP. Hammering it will eventually return code `-412` (anti-crawl). Add a 1–2s pause between calls in tight loops.
- Subtitle fetching is **not** implemented here — that requires `SESSDATA` cookie authentication. A separate `bilibili_subs` server is planned.
- Some queries (especially very generic keywords) may return zero `video` results because B站 prioritizes user/article results in the all/v2 endpoint. Try a more specific query.
