"""Agent runner — executes a single agent run using Claude Code SDK."""

import sqlite3
import time
from dataclasses import dataclass

from .config import AgentRunConfig


@dataclass
class RunResult:
    status: str  # "success" or "error"
    num_turns: int = 0
    duration_ms: int = 0
    error_message: str | None = None
    response_summary: str | None = None
    awakening_id: int | None = None


async def run_agent(config: AgentRunConfig) -> RunResult:
    """Execute a single agent run using Claude Code SDK.

    Builds the MCP server dict and ClaudeCodeOptions from agent-db config,
    then runs the agent and records results.
    """
    start_time = time.monotonic()

    try:
        from claude_code_sdk import ClaudeCodeOptions, query as claude_query

        # Build MCP servers dict
        mcp_servers = {}
        for srv in config.mcp_servers:
            entry = {"command": srv.command}
            if srv.args:
                entry["args"] = srv.args
            if srv.env:
                entry["env"] = srv.env
            mcp_servers[srv.name] = entry

        # Build options
        options = ClaudeCodeOptions(
            system_prompt=config.system_prompt,
            mcp_servers=mcp_servers,
            model=config.model,
            max_turns=config.max_turns,
            permission_mode="acceptall",
        )

        # Execute agent
        messages = []
        async for msg in claude_query(
            prompt=config.initial_prompt,
            options=options,
        ):
            messages.append(msg)

        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Extract summary from last assistant message
        summary = None
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content:
                text = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary = text[:500]
                break

        return RunResult(
            status="success",
            num_turns=len(messages),
            duration_ms=duration_ms,
            response_summary=summary,
        )

    except Exception as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        return RunResult(
            status="error",
            duration_ms=duration_ms,
            error_message=str(e)[:500],
        )


def record_run(config: AgentRunConfig, result: RunResult):
    """Record run result into the agent's database."""
    conn = sqlite3.connect(str(config.db_path))
    try:
        # Insert scheduled_run record
        cursor = conn.execute(
            "INSERT INTO scheduled_runs (status, model, num_turns, duration_ms, "
            "error_message, response_summary, awakening_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                result.status,
                config.model,
                result.num_turns,
                result.duration_ms,
                result.error_message,
                result.response_summary,
                result.awakening_id,
            ),
        )

        # Update schedule config
        conn.execute(
            "UPDATE agent_schedule_config SET "
            "last_run_at = CURRENT_TIMESTAMP, "
            "last_run_status = ?, "
            "last_run_error = ?, "
            "total_runs = total_runs + 1, "
            "updated_at = CURRENT_TIMESTAMP",
            (result.status, result.error_message),
        )
        conn.commit()
    finally:
        conn.close()
