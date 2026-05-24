<div align="center">

<img src="docs/banner.svg" alt="MemoMate · 中文生态 MCP 服务器集合 + 跨工具便携记忆" width="100%"/>

# MemoMate

**一个不断扩展的 MCP 服务器集合 + 便携、可导出的记忆库 —— 全部在一个 Python 仓库里。**

### **简体中文** &nbsp;|&nbsp; [English](README.en.md)

</div>

---

MemoMate 是**一个项目里的两件事**：

1. **`servers/`** —— 一组小而专注的 **MCP 服务器**，专为中文工具生态打造（arXiv、B 站、知乎、微信公众号……）。一个文件夹 = 一个服务器。*这是主角。*
2. **`core/`** —— 一个**轻量、便携的记忆 MCP 服务器**，基于 SQLite + FTS5。单文件存储、跨工具共享、可结构化查询。当 Claude Code 内置 memory 不够用时再用。

两者合起来展示了 MCP 端到端开发：广度（多个实用工具）+ 深度（一个有状态、可导出的存储）。

---

## servers/ —— 主要看点

| 服务器 | 状态 | 功能 |
|---|---|---|
| [`arxiv_search`](servers/arxiv_search/) | 可用 | 通过公开 Atom API 搜 arXiv 论文（零依赖） |
| [`bilibili_search`](servers/bilibili_search/) | 可用 | 搜 B 站视频 + 获取视频详情（零依赖） |
| [`zhihu_search`](servers/zhihu_search/) | 脚手架 | 搜知乎问题与答案 |
| [`wechat_mp`](servers/wechat_mp/) | 脚手架 | 读取公开的微信公众号文章 |

每个 server 是一个独立的目录。新 server 按每日迭代节奏陆续上线。

针对各 IDE（Cursor、Claude Code、Trae、CodeBuddy、通义灵码 IDE……）的接入方式，参见下面的 **[接入你的 AI IDE](#接入你的-ai-ide)**。

---

## 为什么中国 AI IDE 用户需要 MemoMate？

国际 AI 编程工具（Cursor、Claude Code、Cline）擅长生成代码，但它们的 MCP 生态高度偏向西方栈 —— arXiv、GitHub、npm、Stack Overflow。中国开发者经常需要的东西，那些工具覆盖不到：

- 搜 **B 站 / 知乎 / 微信公众号**上的技术文章和教程
- 查 **12306 火车班次**、**高德地图路线**、**豆瓣评分**
- 接入**国内 SaaS**，比如 Notion 国内、飞书、钉钉
- 读**国内 arXiv 镜像 / 中国知网**，而不是慢吞吞的国际 arXiv

**MemoMate 的 `servers/` 集合恰好填补这个空白。** 每个服务器都是一个聚焦于某个中文生态工具的小 MCP 服务器。任何 MCP 兼容的 IDE 都用同样的方式接入。

| 你常用的场景 | 对应的 MemoMate server | 状态 |
|---|---|---|
| 找 B 站视频教程 | `bilibili_search` | ✅ 可用 |
| 查 arXiv 论文 | `arxiv_search` | ✅ 可用 |
| 搜知乎技术回答 | `zhihu_search` | 🚧 计划中（W03） |
| 读公众号长文 | `wechat_mp` | 🚧 计划中（W04） |
| 查火车票 / 排班 | `12306` | 🚧 计划中（W07） |
| 看 GitHub 热门 | `github_trending` | 🚧 计划中（W06） |
| 查豆瓣电影 / 书评 | `douban` | 🚧 计划中（W08） |
| 查中国天气 | `weather_cn` | 🚧 计划中（W06） |
| 搜 HackerNews | `hackernews` | 🚧 计划中（W06） |
| 总结 arXiv 论文（本地 LLM） | `arxiv_summary` | 🚧 计划中（W09） |
| 查 Notion workspace | `notion_query` | 🚧 计划中（W11） |

如果你正在用 **Trae / CodeBuddy / 通义灵码 IDE / Cursor / Claude Code**，并且想让 AI 帮你 *"找一下 B 站讲 LangGraph 的视频"* 或者 *"搜知乎上关于 RAG 评测的回答"* —— MemoMate 就是为你做的。

### 接入你的 AI IDE

MCP 的 JSON 结构在**所有客户端中完全一致**（这是协议标准），不同的只是文件位置和编辑界面。

**通用配置（任何接受 `mcpServers` 字段的地方都能塞进去）**：

```json
{
  "mcpServers": {
    "memomate-bilibili": {
      "command": "uv",
      "args": ["run", "--directory", "D:/project/MemoMate", "memomate-bilibili"]
    },
    "memomate-arxiv": {
      "command": "uv",
      "args": ["run", "--directory", "D:/project/MemoMate", "memomate-arxiv"]
    },
    "memomate": {
      "command": "uv",
      "args": ["run", "--directory", "D:/project/MemoMate", "memomate-core"]
    }
  }
}
```

#### 各 IDE 的配置位置

| IDE | 配置位置 | 备注 |
|---|---|---|
| **Cursor** | `~/.cursor/mcp.json`（或项目级 `.cursor/mcp.json`） | 直接编辑文件，然后重启 Cursor |
| **Claude Code** | `~/.claude.json`（或用 `claude mcp add` 命令） | 推荐用 CLI，见下方 |
| **Trae**（字节跳动） | 设置 → AI 模型 / MCP Servers（菜单随版本变化） | 把上方 `mcpServers` 的条目粘进去；或参考 [Trae 官方文档](https://docs.trae.ai/) |
| **CodeBuddy**（腾讯） | 设置 → Extensions → MCP Servers | 添加 stdio 类型，把命令与参数照 JSON 转写到 UI |
| **通义灵码 IDE**（阿里） | 设置 → AI 增强 → MCP 服务器 | 新增 → stdio → 同上 |
| **Cline / Continue / Zed**（VSCode/JetBrains 系扩展） | 各自的 `settings.json` 里的 `mcpServers` 字段 | 格式相同 |

**Claude Code CLI**（推荐）：

```bash
claude mcp add memomate-bilibili --scope user \
  -- uv run --directory D:/project/MemoMate memomate-bilibili
```

> 这就是 MemoMate 的核心价值 —— **同一个 server，所有 IDE 通用**。在 Cursor 里搜的 B 站视频，用 `save_memory` 记下来，下次切到通义灵码 IDE 直接用 `recall_memory` 就能取出来。

---

## core/ —— 可选的便携记忆服务器

一个长期记忆 MCP 服务器，存储后端是 SQLite + FTS5。数据保存在单个文件 `~/.memomate/memories.db` 里，你可以：

- 用任意 SQLite 工具**直接查看**（DB Browser、DataGrip）
- 复制一个文件**完成备份**
- 通过 Syncthing / Dropbox / Git **在多设备同步**
- 在不同 AI 客户端**共享**（Claude Code / Cursor / Continue / 任何 MCP 兼容客户端 —— 都用同一份记忆）
- 用标签或全文搜索**结构化查询**

### Claude Code 已经有内置 memory，为什么还要 MemoMate？

[Claude Code v2.1+](https://docs.claude.com/en/docs/claude-code) 已经内置了优秀的 memory 功能 —— 你说"记住..."或"remember that..."时它会自动把内容写到 `~/.claude/projects/<project>/memory/*.md`。对大多数工作流，**这就够了** —— 内置 memory 才是你应该用的。

MemoMate 的 memory 服务器填补的是内置无法解决的场景：

| 需求 | 内置 memory | MemoMate `core/` |
|---|---|---|
| 日常"记住这个偏好" | ✅ 最佳 | 大材小用 |
| 项目级笔记 | ✅ 最佳 | 不够自然 |
| **跨工具**记忆（Claude Code + Cursor + Continue + 自定义 Agent） | ❌ 仅 Claude Code | ✅ 任何 MCP 客户端 |
| **结构化查询**（标签 + FTS5） | ❌ 纯 markdown | ✅ SQLite FTS5 + tag 字段 |
| **可编程导出 / 备份 / 检查** | ⚠️ 散落的 markdown 文件 | ✅ 单个便携 `.db` 文件 |
| **用户级**（跨项目）事实 | ⚠️ 单项目作用域 | ✅ 存在 `~/.memomate/` |
| 在你自己的脚本里**编程访问** | ❌ 需要解析 markdown | ✅ 标准 SQL |

下面四行中有任意一个对你重要，就装 `core/`。如果都不需要，跳过 `core/`，只用上面的 servers 就够了。

### 如何明确触发 MemoMate 的 memory

由于 Claude Code 内置 memory 在通用的"记住 / remember"提示下有**系统级优先级**，想用 MemoMate 时要明确点名：

- *"save to MemoMate: ..."*
- *"用 MemoMate 记一下：..."*
- *"recall from memomate: ..."*
- *"列出 memomate 里的记忆"*

这个"显式路由"是有意的设计选择 —— 详见下方 *与内置 memory 共存的设计思路*。

---

## 快速开始

需要 Python 3.11+。本项目用 [`uv`](https://docs.astral.sh/uv/) 做依赖管理。

```bash
# clone 并 install
git clone https://github.com/Mrduan-cloud/MemoMate.git
cd MemoMate
uv sync

# 跑 memory server（可选）
uv run memomate-core

# 跑一个工具 server
uv run memomate-arxiv
```

### 在 AI IDE 里注册

参见上方 **[接入你的 AI IDE](#接入你的-ai-ide)** 的完整说明，覆盖 Cursor、Claude Code、Trae、CodeBuddy、通义灵码 IDE、Cline、Continue、Zed。

---

## 架构

```
MemoMate/
├── core/                       # 记忆 MCP 服务器（可选）
│   ├── server.py               # FastMCP 入口，5 个工具
│   └── store.py                # SQLite + FTS5 存储（WAL 模式支持多客户端并发）
└── servers/                    # 工具 MCP 服务器（主角）
    ├── arxiv_search/           # 可用
    ├── bilibili_search/        # 可用
    ├── zhihu_search/           # 脚手架
    └── wechat_mp/              # 脚手架
```

### Memory 工具（`core/`）

| 工具 | 作用 |
|---|---|
| `save_memory(content, tags?, source?)` | 把一条事实持久化到 SQLite |
| `recall_memory(query, limit=5)` | 在已保存的记忆里做 FTS5 全文搜索 |
| `list_recent_memories(limit=10)` | 按反时间序列列出最近的记忆 |
| `forget_memory(memory_id)` | 按 id 硬删除 |
| `memory_stats()` | 返回总条数和 db 路径 |

### 加一个新的工具 server

1. 在 `servers/<name>/` 下建 `__init__.py`、`__main__.py`、`server.py`、`README.md`。
2. 在 `server.py` 里暴露 `mcp = FastMCP("memomate-<name>")` 和 `main()` 入口。
3. 在 `pyproject.toml` 的 `[project.scripts]` 注册为 `memomate-<name>`。

可以参考 [`servers/arxiv_search/`](servers/arxiv_search/) 的实现作为模板。

---

## 与内置 memory 共存的设计思路

开发过程中，我尝试通过强化工具 docstring 让 MemoMate 的 `save_memory` 成为"记住 X"提示的默认目的地。试了几轮 —— 强化描述、加显式路由提示 —— 都没能盖过 Claude Code 的内置 memory。它的优先级高于用户安装的 MCP 工具。

**经验**不是"Claude Code 内置赢了我的项目"，而是：

> 当你的 MCP 服务器和宿主的官方功能重叠时，**不要在同一个触发词上竞争**。在能力维度差异化（可移植性、查询模型、导出格式），并要求显式路由。

这也是为什么 MemoMate 的主要定位从"你的记忆层"切换到了"你的**便携**记忆层 + 一组实用 MCP 服务器集合"。可移植性和 servers 集合才是内置 memory 给不了的价值。

---

## License

MIT
