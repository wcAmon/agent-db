-- AgentDB Schema
-- Each agent gets its own .db file with these tables.

CREATE TABLE IF NOT EXISTS system_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5 CHECK(priority BETWEEN 1 AND 10),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'done')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    full_doc TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5 CHECK(importance BETWEEN 0.0 AND 1.0),
    mem_type TEXT NOT NULL DEFAULT 'fact' CHECK(mem_type IN ('fact', 'experience', 'insight')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS buffers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success' CHECK(status IN ('success', 'error')),
    input_summary TEXT,
    output_summary TEXT,
    duration_ms INTEGER,
    source TEXT NOT NULL DEFAULT 'auto' CHECK(source IN ('auto', 'manual')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS awakenings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loaded_system_prompt_version INTEGER,
    loaded_todos TEXT,
    loaded_skills TEXT,
    loaded_memories TEXT,
    loaded_buffers TEXT,
    loaded_tool_calls TEXT,
    total_tokens INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent 可用的 MCP Server 設定（per-agent）
CREATE TABLE IF NOT EXISTS mcp_servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    server_type TEXT NOT NULL DEFAULT 'stdio' CHECK(server_type IN ('stdio', 'sse')),
    command TEXT NOT NULL,
    args TEXT,          -- JSON array
    env TEXT,           -- JSON object
    is_enabled BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 排程設定（每個 agent 一筆）
CREATE TABLE IF NOT EXISTS agent_schedule_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    is_enabled BOOLEAN NOT NULL DEFAULT 0,
    interval_seconds INTEGER NOT NULL DEFAULT 300,
    max_turns INTEGER NOT NULL DEFAULT 20,
    model TEXT NOT NULL DEFAULT 'claude-sonnet-4-5',
    initial_prompt TEXT NOT NULL DEFAULT 'Start by calling awaken with include_tool_history=true, then act according to your system prompt.',
    last_run_at TIMESTAMP,
    last_run_status TEXT CHECK(last_run_status IN ('success', 'error')),
    last_run_error TEXT,
    total_runs INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 排程執行記錄
CREATE TABLE IF NOT EXISTS scheduled_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running', 'success', 'error')),
    model TEXT,
    num_turns INTEGER,
    duration_ms INTEGER,
    error_message TEXT,
    response_summary TEXT,
    awakening_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
CREATE INDEX IF NOT EXISTS idx_todos_priority ON todos(priority DESC);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);
CREATE INDEX IF NOT EXISTS idx_system_prompts_active ON system_prompts(is_active);
CREATE INDEX IF NOT EXISTS idx_awakenings_created ON awakenings(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_name ON tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_calls_created ON tool_calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled ON mcp_servers(is_enabled);
CREATE INDEX IF NOT EXISTS idx_scheduled_runs_created ON scheduled_runs(created_at DESC);
