# WEEKLY_LOG · MemoMate

> 每周复盘。Phase 1（90 天开局冲刺）按周轮转，周日把本周 `.scratch/daily-*` 汇总到这里。
> 自研 MCP 工具集，体现 MCP 协议 + 中文生态工具开发能力。

---

## W01 · 2026-05-25 → 2026-05-31 · 轮值副项目（arxiv_search 测试 + 加固）

> 本周角色：W01 主项目是 NutriCore，MemoMate 作为轮值副项目在周四推进（本周首次碰它）。

### 这周做了什么

| 日期 | commit | 内容 |
|---|---|---|
| 5/28 Day4 | `b59ff34` | 给**零测试**的 `arxiv_search` server 补覆盖：为可测而做最小重构——从 `_fetch` 抽出纯函数 `_build_url(query, max_results, sort_by)`（无 I/O，行为不变），让 query 构造脱离网络可单测。20 个测试覆盖字段前缀 `ti:`/`au:`/`cat:` 的 URL 编码 round-trip、特殊字符百分号编码、`max_results` clamp 到 `[1,30]`、Atom XML 解析的缺失字段 / 多作者 / 空白归一化；live 测试 `@pytest.mark.network` 默认 deselect，遇 429 限流 skip 而非 fail |
| 5/28 Day4 | `3824779` | self-review 冷读整个 server.py（不只看新 diff），抓出 2 个既有问题：明文 `http://` 端点（查询明文 + MITM 可篡改返回 XML）→ 改 `https://`；`xml.etree.fromstring` 解析远程 XML 无兜底（billion-laughs DoS 警告）→ catch `ParseError` 返 `[]`。一字 `http→https` 同时缓解两点，保住 zero-dependency 卖点。4 个新测试（含"合法但无 entry" vs "畸形不闭合"两条路径分别覆盖），总测试 12 → 36 |

### 现状

- ✅ `arxiv_search` 测试覆盖 + 安全加固完成（36 测试全过，ruff clean）
- 此前已有 `bilibili_search`（可用）；plan W03（6/8 起）将扩 `zhihu_search` 等更多 server

### 收获

1. **"为了可测而做的最小重构"是标准操作，不是过度设计**：抽 `_build_url` 这种 I/O 分离，和 NutriCore 的意图分类注入点、MediRead 的 verify 脚本同一手法——让纯逻辑脱离副作用从而可单测。
2. **live API 测试遇限流要 skip 不要 fail**：429 ≠ 代码坏，这是 `@network` 测试默认 deselect 的根本原因。
3. **`/code-review` 要冷读改动周围的既有代码**：本周第 3 次 self-review 抓既有代码问题（5/26 paddle pin / 5/27 多模态 gate / 5/28 arxiv http）——模式已稳定。
4. **合法 XML ≠ 期望的 XML**：`<html>...</html>` 闭合标签合法（走"无 entry"路径），测兜底分支要用真畸形（不闭合）输入。
5. **环境坑**：MCP server 运行时 `memomate-core.exe` 被文件锁，`uv run --no-sync` 跳过 sync 用现有 venv。

---
