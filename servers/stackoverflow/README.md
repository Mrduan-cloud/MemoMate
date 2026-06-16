# stackoverflow

MCP server for **Stack Overflow** — official Stack Exchange API, **no API key**.

**Zero external dependencies** — stdlib only (`urllib`, `json`, `re`, `html`, `gzip`)。搜问题走
`/2.3/search/advanced`,取答案正文走 `/2.3/questions/{id}/answers?filter=withbody`,均免 key
(匿名配额约 300 次/天/IP)。

## Tools

| Tool | Description |
|---|---|
| `search_stackoverflow(query, tag="", limit=10, sort="relevance")` | 搜问题:`id` / `title` / `score` / `answers`(答案数)/ `is_answered` / `accepted`(是否有被采纳答案)/ `tags` / `views` / `age`(m/h/d)/ `link`。 |
| `get_stackoverflow_answers(question_id, limit=3)` | 取某问题答案(按得票降序):`id` / `score` / `is_accepted` / `author` / `body`(HTML 转纯文本)/ `link` / `age`。 |

- `sort`：`relevance` / `votes` / `creation` / `activity`（也认 `相关` / `高赞` / `最新` / `活跃`），默认 `relevance`。
- `tag`：可选标签过滤（如 `python`、`rust`；多个用 `;` 分隔）。
- `search_stackoverflow` 的 `limit` clamp 到 1..30；`get_stackoverflow_answers` 的 `limit` clamp 到 1..10。

## How it works

- 两个端点都是单次请求(非「列表→逐条」),各消耗 1 次配额。
- 自我限流:每次工具调用入口 acquire 一次(≥0.5s/次,与本仓其它 server 同款 `_RateLimiter`)。
- 解析/归一全部纯函数化(`_normalize_sort` / `_search_url` / `_answers_url` / `_normalize_question` / `_normalize_answer` / `_html_to_text` / `_humanize_age`),离线可单测。
- 答案 `body` 是 HTML → 用 stdlib 正则转可读纯文本(块级标签转换行、去标签、解实体、压空白;代码块文本保留)。
- 优雅降级:网络/解析错误返回 `[]`;个别条目坏掉(无 `question_id` / `answer_id`)只跳过该条。

## 实测要点(对真实 SE API 定)

- urllib(不发 `Accept-Encoding`)拿到的是**未压缩** JSON;但官方文档声明「响应总是 gzip」,故 `_fetch_json` 仍按魔数 `\x1f\x8b` 防御性解压,两种都吃得下。
- 问题无被采纳答案时,`accepted_answer_id` **字段缺失**(不是 `null`)→ 用其「是否存在」判 `accepted`;`is_answered` 才是「有没有答案」的可靠信号。
- 答案对象不含 `link` 字段 → 用规范短链 `stackoverflow.com/a/{answer_id}` 构造(302 跳到答案锚点)。

## Example prompts

- *"在 Stack Overflow 搜搜 `asyncio gather` 怎么用,给我几个高票问题。"*
- *"用 memomate-stackoverflow 查 rust 标签下 tokio 运行时相关的高赞问题。"*
- *"把这个问题的被采纳答案正文取出来:question_id=11236129。"*

## Plug into Claude Code

```bash
claude mcp add memomate-stackoverflow --scope user \
  -- uv run --directory D:/project/MemoMate memomate-stackoverflow
```

## Limitations

- 匿名调用受配额限制(约 300 次/天/IP,无 key)。需要更高配额或写操作时,SE 支持注册 app key,本 server 暂未接(只读、低频足够)。
- 仅查 `stackoverflow` 站点;Stack Exchange 网络其它站点(superuser / askubuntu 等)暂未参数化。
- 搜索是全文相关度匹配,`sort=relevance` 由 SE 侧打分,本 server 不二次排序。
