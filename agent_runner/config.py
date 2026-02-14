"""Configuration loading for scheduled agent runs."""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class McpServerConfig:
    name: str
    command: str
    args: list[str] | None = None
    env: dict[str, str] | None = None


@dataclass
class AgentRunConfig:
    agent_id: str
    db_path: Path
    system_prompt: str
    mcp_servers: list[McpServerConfig] = field(default_factory=list)
    is_enabled: bool = False
    interval_seconds: int = 300
    max_turns: int = 20
    model: str = "claude-sonnet-4-5"
    initial_prompt: str = "Start by calling awaken with include_tool_history=true, then act according to your system prompt."
    last_run_at: str | None = None
    total_runs: int = 0


def load_agent_config(agent_id: str, agents_dir: Path) -> AgentRunConfig | None:
    """Load agent configuration from its SQLite database."""
    db_path = agents_dir / f"{agent_id}.db"
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Get active system prompt
        row = conn.execute(
            "SELECT content FROM system_prompts WHERE is_active = 1 "
            "ORDER BY version DESC LIMIT 1"
        ).fetchone()
        system_prompt = row["content"] if row else ""

        # Get schedule config
        sched = conn.execute("SELECT * FROM agent_schedule_config LIMIT 1").fetchone()
        is_enabled = False
        interval_seconds = 300
        max_turns = 20
        model = "claude-sonnet-4-5"
        initial_prompt = "Start by calling awaken with include_tool_history=true, then act according to your system prompt."
        last_run_at = None
        total_runs = 0
        if sched:
            is_enabled = bool(sched["is_enabled"])
            interval_seconds = sched["interval_seconds"]
            max_turns = sched["max_turns"]
            model = sched["model"]
            initial_prompt = sched["initial_prompt"]
            last_run_at = sched["last_run_at"]
            total_runs = sched["total_runs"]

        # Get enabled MCP servers
        mcp_servers = []
        for srv in conn.execute(
            "SELECT name, command, args, env FROM mcp_servers WHERE is_enabled = 1"
        ).fetchall():
            mcp_servers.append(McpServerConfig(
                name=srv["name"],
                command=srv["command"],
                args=json.loads(srv["args"]) if srv["args"] else None,
                env=json.loads(srv["env"]) if srv["env"] else None,
            ))

        return AgentRunConfig(
            agent_id=agent_id,
            db_path=db_path,
            system_prompt=system_prompt,
            mcp_servers=mcp_servers,
            is_enabled=is_enabled,
            interval_seconds=interval_seconds,
            max_turns=max_turns,
            model=model,
            initial_prompt=initial_prompt,
            last_run_at=last_run_at,
            total_runs=total_runs,
        )
    except sqlite3.OperationalError:
        # Tables might not exist yet
        return None
    finally:
        conn.close()
