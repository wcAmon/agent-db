# AgentDB

MCP-based agent memory management system with layered awakening.

Each agent gets its own SQLite database. An MCP server exposes tools for managing context (system prompts, todos, memories, skills, buffers, tool calls). A Flask dashboard provides a web UI and REST API for monitoring and administration.

## Architecture

```
Worker Agent ──► MCP Server (agent_id scoped tools)
                     │
                     ▼
               SQLite per agent  ◄── Dashboard (read-only views + admin API)
                 (WAL mode)
```

**Key design decisions:**

- **Layered awakening** — loads ~5K tokens instead of 50K+ by selecting top priorities, top memories, skill metadata only, and buffer titles only
- **Per-agent isolation** — each agent has its own `.db` file; no cross-agent data leakage
- **WAL mode** — concurrent readers never block writers
- **Auto-logging** — `AutoLoggingMCP` proxy records every tool call with timing, input/output summaries, without blocking tool execution

## Project Structure

```
agent-db/
├── agentdb_server/              # MCP server
│   ├── server.py                # Entry point, tool registration
│   ├── db.py                    # DatabaseManager (connections, migrations)
│   ├── schema.sql               # SQLite schema (7 tables)
│   ├── tool_logger.py           # AutoLoggingMCP proxy
│   └── tools/
│       ├── awaken.py            # Layered awakening (6 layers)
│       ├── todo.py              # Todo CRUD
│       ├── memory.py            # Memory store & search
│       ├── skill.py             # Skill catalog
│       ├── buffer.py            # Long document storage
│       └── tool_call.py         # Tool call logging & stats
├── dashboard/                   # Flask web app
│   ├── app.py                   # Routes (index, agent detail, admin)
│   ├── api.py                   # REST API blueprint (/api)
│   ├── models.py                # SQLAlchemy ORM models
│   └── templates/
│       ├── base.html            # Dark theme base layout
│       ├── index.html           # Agent list
│       ├── agent_detail.html    # Agent overview
│       ├── awakening_detail.html
│       └── admin.html           # Cross-agent admin overview
├── tests/
│   ├── test_core.py             # DB layer + schema tests
│   └── test_api.py              # REST API endpoint tests
└── pyproject.toml
```

## Quick Start

### Install

```bash
pip install -e ".[dashboard,dev]"
```

### Run MCP Server

```bash
# Default agents directory: ./agents
agentdb-server

# Custom directory
AGENTDB_AGENTS_DIR=/path/to/agents agentdb-server
```

### Run Dashboard

```bash
agentdb-dashboard
# Serves at http://localhost:5000
```

### Run Tests

```bash
pytest tests/ -v
```

## MCP Tools

### Awakening

| Tool | Description |
|------|-------------|
| `awaken(agent_id, include_tool_history?)` | Load 6-layer context (~5K tokens) |
| `update_system_prompt(agent_id, content)` | Create new prompt version |
| `get_system_prompt(agent_id)` | Get active system prompt |

**Awakening layers:**

| Layer | Content | Budget |
|-------|---------|--------|
| 1 | Active system prompt | ~500 tokens |
| 2 | Top 5 pending todos by priority | ~200 tokens |
| 3 | Skills catalog (metadata only) | ~1000 tokens |
| 4 | Top 10 memories by importance | ~3000 tokens |
| 5 | Buffer references (titles only) | minimal |
| 6 | Recent 20 tool calls (optional) | ~300 tokens |

### Todos

| Tool | Description |
|------|-------------|
| `add_todo(agent_id, content, priority?)` | Add todo (priority 1-10) |
| `list_todos(agent_id, status?)` | List todos, filter by status |
| `complete_todo(agent_id, todo_id)` | Mark todo as done |

### Memories

| Tool | Description |
|------|-------------|
| `remember(agent_id, title, content, importance?, mem_type?)` | Store memory (importance 0.0-1.0, type: fact/experience/insight) |
| `search_memories(agent_id, query, limit?)` | Keyword search, ordered by importance |
| `get_memory(agent_id, memory_id)` | Get single memory |

### Skills

| Tool | Description |
|------|-------------|
| `add_skill(agent_id, category, name, description, full_doc?)` | Add to catalog |
| `get_skill_catalog(agent_id)` | Metadata by category (no full_doc) |
| `load_skill(agent_id, skill_id)` | Load full documentation |

### Buffers

| Tool | Description |
|------|-------------|
| `store_buffer(agent_id, title, content)` | Store long document |
| `load_buffer(agent_id, buffer_id)` | Load full content |
| `list_buffers(agent_id)` | List titles only |

### Tool Calls

| Tool | Description |
|------|-------------|
| `log_tool_call(agent_id, tool_name, status?, ...)` | Manually log external tool usage |
| `list_tool_calls(agent_id, tool_name?, limit?)` | Query call history |
| `get_tool_stats(agent_id)` | Per-tool stats: count, success/error rate, avg duration |

## Dashboard REST API

Base URL: `http://localhost:5000/api`

### Agents

```
GET    /api/agents                              # List all agents with stats
```

### Per-Agent Resources

Each resource supports full CRUD at `/api/agents/{id}/{resource}`:

```
GET    /api/agents/{id}/memories                # List
GET    /api/agents/{id}/memories/{mid}          # Detail
POST   /api/agents/{id}/memories                # Create
PUT    /api/agents/{id}/memories/{mid}          # Update
DELETE /api/agents/{id}/memories/{mid}          # Delete
```

Same pattern applies to: `todos`, `skills`, `buffers`, `system_prompts`.

### Tool Calls & Awakenings (read-only)

```
GET    /api/agents/{id}/tool_calls?tool_name=&limit=   # Call history
GET    /api/agents/{id}/tool_calls/stats                # Aggregated stats
GET    /api/agents/{id}/awakenings                      # Awakening history
GET    /api/agents/{id}/awakenings/{aid}                # Awakening detail
```

### Examples

```bash
# List agents
curl http://localhost:5000/api/agents

# Create a memory
curl -X POST http://localhost:5000/api/agents/my-agent/memories \
  -H 'Content-Type: application/json' \
  -d '{"title": "API pattern", "content": "Use REST conventions", "importance": 0.8}'

# Get tool call stats
curl http://localhost:5000/api/agents/my-agent/tool_calls/stats
```

## Database Schema

Each agent's SQLite database contains 7 tables:

| Table | Purpose |
|-------|---------|
| `system_prompts` | Versioned behavioral guidelines |
| `todos` | Task items with priority (1-10) and status |
| `memories` | Knowledge notes with importance (0.0-1.0) and type |
| `skills` | Skill catalog with metadata + full documentation |
| `buffers` | Long document storage |
| `tool_calls` | Tool invocation history with timing and status |
| `awakenings` | Snapshots of what was loaded during each awakening |

## Auto-Logging

The `AutoLoggingMCP` proxy wraps tool registration so that every tool call is automatically recorded:

- **Timing** — duration in milliseconds
- **Input summary** — JSON with large fields truncated to 200 chars
- **Output summary** — truncated to 500 chars
- **Silent failure** — logging errors never block tool execution
- **Exclusions** — `log_tool_call`, `list_tool_calls`, `get_tool_stats` are excluded to prevent recursion

## Claude Code Integration

Add to your Claude Code MCP config:

```json
{
  "mcpServers": {
    "agentdb": {
      "command": "agentdb-server",
      "env": {
        "AGENTDB_AGENTS_DIR": "/path/to/agents"
      }
    }
  }
}
```

## License

MIT
