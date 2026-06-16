# MemoMate Servers · 速查目录

一页看完所有可用 MCP server:**能问它什么** + 三个可直接对 AI IDE 说的示例 prompt。
每个 server 独立可插拔,接入方式见各自目录下的 `README.md` 或主 [`README.md`](README.md#接入你的-ai-ide)。

> 状态总览与「如何新增一个 server」见 [`servers/README.md`](servers/README.md)。

| Server | 入口 | 一句话 |
|---|---|---|
| [`arxiv_search`](servers/arxiv_search/) | `memomate-arxiv` | 通过公开 Atom API 搜 arXiv 论文(零依赖) |
| [`bilibili_search`](servers/bilibili_search/) | `memomate-bilibili` | 搜 B 站视频 + 视频详情 + 取字幕转写(零依赖) |
| [`zhihu_search`](servers/zhihu_search/) | `memomate-zhihu` | 搜知乎问题/答案 + 取答案正文(限流 + 24h 缓存) |
| [`weather_cn`](servers/weather_cn/) | `memomate-weather` | 中文城市天气 + 3 天预报,wttr.in 免 key(零依赖) |
| [`github_trending`](servers/github_trending/) | `memomate-github-trending` | GitHub 热门仓库 daily/weekly/monthly + 语言过滤(零依赖) |
| [`hackernews`](servers/hackernews/) | `memomate-hackernews` | Hacker News 榜单 + 全文检索,官方 API + Algolia(零依赖) |
| [`wechat_mp`](servers/wechat_mp/) | `memomate-wechat-mp` | 解析公开微信公众号文章:标题/公众号/作者/时间/正文(零依赖) |
| [`stackoverflow`](servers/stackoverflow/) | `memomate-stackoverflow` | 搜 Stack Overflow 问题 + 取答案正文,官方 API 免 key(零依赖) |

> 另有 [`core`](core/)(可选记忆 server,SQLite + FTS5,5 个工具)。

---

## arxiv_search — 学术论文

`search_arxiv(query, max_results=5, sort_by="relevance")`,支持 `ti:` / `au:` / `abs:` / `cat:` 前缀。

- *"搜一下关于 mixture of experts 的最新 arXiv 论文。"*
- *"用 memomate-arxiv 查 `au:lecun` 的论文,按时间排。"*
- *"Find recent arXiv papers on retrieval-augmented generation."*

## bilibili_search — B 站视频

`search_bilibili_videos` / `get_video_info(bvid)` / `get_video_subtitles(bvid)`(取字幕需 `BILIBILI_SESSDATA`)。

- *"Search B站 for videos about LangGraph tutorials."*
- *"用 memomate-bilibili 找一下 RAG 入门视频,给我前 5 个。"*
- *"取一下 BV1xx411c7mD 的字幕转写。"*

## zhihu_search — 知乎问答

`search_zhihu(query, kind="question"|"answer", limit=5)` / `fetch_answer(answer_id)`(限流 + 24h 缓存)。

- *"在知乎搜搜『RAG 和微调怎么选』,给我几个高赞回答。"*
- *"用 memomate-zhihu 找『LangGraph 怎么用』相关的问题。"*
- *"把这条知乎答案的正文取出来:<答案 URL>。"*

## weather_cn — 天气

`get_weather(city)` / `get_forecast(city, days=3)`(wttr.in,免 key)。

- *"北京今天天气怎么样?"*
- *"用 memomate-weather 查一下杭州未来三天的天气,周末适合骑行吗?"*
- *"What's the weather in Chengdu?"*

## github_trending — GitHub 热门

`get_github_trending(language="", since="daily", limit=15)`(daily/weekly/monthly + 语言过滤)。

- *"看看今天 GitHub 上 Python 的热门项目。"*
- *"用 memomate-github-trending 查本周 Rust trending 前 10。"*
- *"What's trending on GitHub this month?"*

## hackernews — Hacker News

`get_hackernews_stories(category="top", limit=15)`(top/new/best/ask/show/job)/ `search_hackernews(query)`。

- *"看看 Hacker News 今天的热门帖子前 10。"*
- *"用 memomate-hackernews 查 Ask HN 最新都在聊什么。"*
- *"Search Hacker News for posts about Rust async runtimes."*

## wechat_mp — 微信公众号文章

`fetch_wechat_article(url)`(给定公开文章链接 → 标题/公众号/作者/发布时间/正文纯文本)。

- *"帮我把这篇公众号文章读出来:https://mp.weixin.qq.com/s/xxxx"*
- *"用 memomate-wechat-mp 取一下这篇推文的标题、公众号和正文。"*
- *"Summarize this WeChat article: <mp.weixin.qq.com link>。"*

## stackoverflow — Stack Overflow 问答

`search_stackoverflow(query, tag="", limit=10, sort="relevance")` / `get_stackoverflow_answers(question_id, limit=3)`(官方 Stack Exchange API,免 key)。

- *"在 Stack Overflow 搜搜 `asyncio gather` 怎么用,给我几个高票问题。"*
- *"用 memomate-stackoverflow 查 rust 标签下 tokio 运行时相关的高赞问题。"*
- *"把这个 SO 问题的被采纳答案正文取出来:question_id=11236129。"*
