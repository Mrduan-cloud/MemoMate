# arxiv_search

MCP server for searching arXiv papers via the public Atom API.

**Zero external dependencies** — uses only the Python standard library (`urllib`, `xml.etree`).

## Tools

| Tool | Description |
|---|---|
| `search_arxiv(query, max_results=5, sort_by="relevance")` | Search arXiv papers and return id, title, authors, abstract, urls. |

## Query syntax

arXiv supports field prefixes:

| Prefix | Meaning | Example |
|---|---|---|
| `ti:` | title | `ti:"large language model"` |
| `au:` | author | `au:lecun` |
| `abs:` | abstract | `abs:"mixture of experts"` |
| `cat:` | category | `cat:cs.AI` |

Combine with `AND` / `OR` / `ANDNOT`. Example:

```
ti:agent AND cat:cs.AI AND submittedDate:[202401010000 TO 202612310000]
```

## Plug into Claude Code

```json
{
  "mcpServers": {
    "memomate-arxiv": {
      "command": "uv",
      "args": ["run", "--directory", "D:/project/MemoMate", "memomate-arxiv"]
    }
  }
}
```

Then ask: *"Find the 3 most recent papers on RAG evaluation."*
