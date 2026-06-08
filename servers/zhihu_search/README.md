# zhihu_search

> **Status:** available — search + answer fetch implemented (zero external deps).

搜知乎问题/答案的 MCP server。零第三方依赖(stdlib HTTP + JSON)。

## Tools

| Tool | Description |
|---|---|
| `search_zhihu(query, kind="question"\|"answer", limit=5)` | 按关键词搜知乎问题或答案;`limit` 截断到 1..20,`kind` 非法值回退 `question`。 |
| `fetch_answer(answer_id)` | 取单条答案正文(纯文本)。接受裸 id 或完整答案 URL。 |

## 运行

```bash
uv run memomate-zhihu          # stdio MCP server
# 或
python -m servers.zhihu_search
```

接入 AI IDE 的 `mcpServers` 配置同其他 server(见仓库根 README),把命令换成 `memomate-zhihu`。

## 实现要点

- 走公开 `www.zhihu.com/api/v4/search_v3`(`t=general`)+ 真实浏览器 UA,先访问首页**预热 cookie**。
- **自我限流**:`_RateLimiter` 默认调用间隔 ≥ 2s(知乎封得快,先自我节流);`wait_seconds()` 为纯函数、可单测。
- **优雅降级**:被反爬/限流(4xx / 非 JSON)时 `search_zhihu` 返回 `[]`、`fetch_answer` 返回带 `error` 的 dict,不向 MCP 客户端抛异常。
- `search_v3` 返回混合对象类型 + `relevant_query`/`search_club` 噪声行,客户端按 `kind` 过滤、`.get()` 防御式解析。

## 后续(超出本 scaffold)

- 结果缓存(24h,`~/.memomate/zhihu_cache.db`)避免重复打点。
- `_RateLimiter` 升级为令牌桶 / 持久化窗口(跨进程限流)。
- 答案正文保留富文本结构(图片/代码块)而非纯文本。

## 测试

`tests/test_zhihu_search.py` 覆盖纯逻辑(kind 归一化 / URL 构造 / HTML 清洗 / 搜索体解析过滤 / 限流数学);live 网络测试带 `@pytest.mark.network`,默认 deselect,`pytest -m network` 显式开启。
