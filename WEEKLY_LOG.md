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

## W03 · 2026-06-08 → 2026-06-14 · 主项目（MemoMate servers MVP）

> 本周角色：MemoMate 首次当**主项目**（周一/三/五重头戏），MediRead / NutriCore 周二/周四轮值维护。
> 实际节奏：W03 五天日任务在一个工作日内**全部前移做完**，本节按 plan 日期归档。

### 这周做了什么

| 日期 | 项目 · PR | 内容 |
|---|---|---|
| 6/8 周一 | MemoMate `#6` | `zhihu_search` 加 **24h SQLite 结果缓存**（stdlib 零依赖）：纯函数化 `cache_key`/`is_fresh`（含时钟偏移防护）可离线单测；SQLite 层全程优雅降级（坏缓存不拖累搜索）；**只缓存非空结果**（被反爬挡掉返回 `[]` 不写，便于尽快重试）。zhihu 主体（search+限流+fetch_answer）在 W02 末已前移建掉（#5），本周补缓存闭环。 |
| 6/9 周二 | MediRead `#16` | `parser/normalizer` 加**血糖 mg/dL ↔ mmol/L 单位归一化**：纯函数 `normalize_glucose_value(name,value,unit)`，**只动血糖的 mg/dL**（换算因子 18.0），绝不误改同名单位的其它指标（胆固醇等）；接进 extractor 在 name 归一化之后、异常判定之前，使 KB 参考范围（按 mmol/L）口径一致。+6 测试。 |
| 6/11 周四 | NutriCore `#19` | `nutritionist/tools` 把 **BMI / 每日能量目标包成 LangChain Function Calling 工具**：散落在 memory/meal_plan/risk_screening 的算法收敛成「纯函数内核 + `@tool` 外壳」；外壳做中文别名归一化 + 异常兜底（脏输入返回友好提示而非抛栈，不打断 LangGraph）；**安全下限：能量目标永不低于 BMR**。14 测试进 CI 纯逻辑清单，同步修了 prompts 里"预告但不存在"的工具名。 |
| 6/12 周五 | MemoMate `#7` | `bilibili_search` 加 **`get_video_subtitles`**（字幕→带时间轴分段 + 纯文本转写）：B站只对登录态返回字幕 URL，故 SESSDATA 走 **`BILIBILI_SESSDATA` 环境变量**即时读取注入 cookie jar（**绝不日志/落盘/提交**）；三步链路 view→player/v2→CDN，复用 `_RateLimiter` 自限流；未授权优雅降级回带 `available_langs`。18 测试。 |
| 6/13 周六 | MemoMate `#8` | `zhihu_search` 补**离线 mock-HTTP 端到端测试**：monkeypatch `_new_opener`/`_cache`/`_limiter`，覆盖命中/缓存/降级/只缓存非空四条语义路径，`_DictCache` 桩替真实 SQLite 零副作用。全量 81 passed。 |

### 现状

- ✅ MemoMate 三个工具 server 都成型：`arxiv`（W01 加固）· `zhihu`（search+fetch+限流+24h 缓存,含 mock-HTTP 测试）· `bilibili`（search+info+**字幕**）。三仓 main 全绿。
- 🟡 后台挂着 1 个去重 chip：`meal_plan.generator._estimate_target_kcal` 复用新的 `mifflin_st_jeor_bmr`（需保数值一致,别动 test_plan_eval）。
- 纯视觉待人眼看：NutriCore 日/月切换 · MemoMate 落地页（已上线但单看 PR 看不出）。

### 收获

1. **需要登录的能力,凭证一律走 env + 即时读取**：SESSDATA 不进代码、不进日志、不进缓存,调用时从 `BILIBILI_SESSDATA` 读;未授权不报错而回带 `available_langs` 让调用方自查——既守住安全红线又不牺牲可用性。这是本周最该带走的一条。
2. **「纯函数内核 + 薄外壳」让 @tool / @mcp.tool 也能纳入 CI**：`@tool` 对象的 `.invoke({...})` 在无 LLM 环境可直接调,配合纯内核单测,Function Calling / MCP 工具的核心逻辑都能进纯逻辑守护;外壳只担参数归一化 + 异常兜底。
3. **缓存/降级语义用「打了几次网络」断言**：假 opener 记 `calls` 次数,比断返回值更能锁住"二次命中不重复打网""失败不固化缓存"这类行为契约。
4. **「文档先行的工具名」是收敛信号**：prompts 预告了 `bmi_calc/energy_target` 却无实现——三连查抓到这种欠账,顺手既补功能又消文档漂移。
5. **节奏观察**：W03 整周日任务一天清完(且 6/10 fetch_answer 早在 W02 末前移)。前移要在日报对账里显式记,否则下次易重造。

### 下周预告 · W04（06/15–06/21）· MediRead RAG 与医学知识库

主项目切回 **MediRead**,本周搭医学解读 Agent 的 RAG 底座：
- 6/15 `feat(data/kb)`：5 个常见血/尿指标 markdown 知识文件 ⭐⭐⭐
- 6/17 `feat(clients/milvus)`：KB markdown 索引进 `medical_kb` collection（带元数据)⭐⭐⭐
- 6/19–6/20：BM25 + BGE 多路召回 + RRF 融合 → Cross-Encoder 精排（top-20→top-5）+ recall 测试 ⭐⭐⭐
- 轮值:6/16 MemoMate `weather_cn`(wttr.in)· 6/18 NutriCore meal_plan recall@5≥0.8 固化

---
