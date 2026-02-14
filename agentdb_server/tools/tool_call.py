"""Tool call logging and statistics tools."""

import json

from agentdb_server.db import DatabaseManager


def register(mcp, db: DatabaseManager):
    @mcp.tool()
    def log_tool_call(
        agent_id: str,
        tool_name: str,
        status: str = "success",
        input_params: str = "",
        output_result: str = "",
        duration_ms: int = 0,
    ) -> dict:
        """Manually log an external tool call.

        Args:
            agent_id: The agent's identifier.
            tool_name: Name of the tool that was called.
            status: 'success' or 'error'.
            input_params: Optional JSON string of input parameters.
            output_result: Optional JSON string of output/result.
            duration_ms: Optional execution time in milliseconds.
        """
        if status not in ("success", "error"):
            return {"error": "status must be 'success' or 'error'"}

        conn = db.get_write_connection(agent_id)
        conn.execute(
            "INSERT INTO tool_calls (tool_name, status, input_summary, output_summary, "
            "duration_ms, source) VALUES (?, ?, ?, ?, ?, 'manual')",
            (
                tool_name,
                status,
                input_params[:200] if input_params else None,
                output_result[:500] if output_result else None,
                duration_ms,
            ),
        )
        conn.commit()

        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return {"id": row_id, "tool_name": tool_name, "status": status}

    @mcp.tool()
    def list_tool_calls(
        agent_id: str,
        tool_name: str = "",
        limit: int = 20,
    ) -> list[dict]:
        """List recent tool call records for an agent.

        Args:
            agent_id: The agent's identifier.
            tool_name: Optional filter by tool name.
            limit: Max number of records (default 20).
        """
        conn = db.get_write_connection(agent_id)
        limit = max(1, min(limit, 100))

        if tool_name:
            rows = conn.execute(
                "SELECT id, tool_name, status, input_summary, output_summary, "
                "duration_ms, source, created_at FROM tool_calls "
                "WHERE tool_name = ? ORDER BY created_at DESC LIMIT ?",
                (tool_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, tool_name, status, input_summary, output_summary, "
                "duration_ms, source, created_at FROM tool_calls "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [dict(r) for r in rows]

    @mcp.tool()
    def get_tool_stats(agent_id: str) -> list[dict]:
        """Get aggregated tool call statistics for an agent.

        Returns per-tool: call count, success/error counts, average duration.
        """
        conn = db.get_write_connection(agent_id)
        rows = conn.execute(
            "SELECT tool_name, "
            "COUNT(*) as total_calls, "
            "SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count, "
            "SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count, "
            "AVG(duration_ms) as avg_duration_ms "
            "FROM tool_calls GROUP BY tool_name ORDER BY total_calls DESC"
        ).fetchall()
        return [dict(r) for r in rows]
