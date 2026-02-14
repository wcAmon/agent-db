"""Auto-logging proxy for MCP tool calls.

Wraps MCPServer's tool() decorator to automatically record every tool
invocation into the agent's tool_calls table.
"""

import json
import time
import traceback
from functools import wraps

from agentdb_server.db import DatabaseManager


def _truncate(value, max_len: int) -> str | None:
    """Truncate a string to max_len characters."""
    if value is None:
        return None
    s = str(value)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def _summarize_input(params: dict, max_len: int = 200) -> str | None:
    """Create a truncated JSON summary of input params, filtering large fields."""
    if not params:
        return None
    filtered = {}
    large_fields = {"content", "full_doc", "document", "text", "body"}
    for k, v in params.items():
        if k in large_fields and isinstance(v, str) and len(v) > 100:
            filtered[k] = v[:100] + "..."
        else:
            filtered[k] = v
    return _truncate(json.dumps(filtered, ensure_ascii=False, default=str), max_len)


class AutoLoggingMCP:
    """Proxy that wraps MCPServer.tool() to auto-log calls to tool_calls table.

    Usage:
        logged_mcp = AutoLoggingMCP(mcp, db, exclude={"log_tool_call", ...})
        # Use logged_mcp.tool() instead of mcp.tool() for auto-logged tools
    """

    def __init__(self, mcp, db: DatabaseManager, exclude: set[str] | None = None):
        self._mcp = mcp
        self._db = db
        self._exclude = exclude or set()

    def tool(self):
        """Return a decorator that wraps the tool function with auto-logging."""
        original_decorator = self._mcp.tool()

        def decorator(fn):
            tool_name = fn.__name__

            if tool_name in self._exclude:
                return original_decorator(fn)

            @wraps(fn)
            def wrapper(*args, **kwargs):
                # Extract agent_id from first arg or kwargs
                agent_id = kwargs.get("agent_id") or (args[0] if args else None)
                start = time.monotonic()
                status = "success"
                result = None
                try:
                    result = fn(*args, **kwargs)
                    return result
                except Exception:
                    status = "error"
                    result = traceback.format_exc()
                    raise
                finally:
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    self._log(
                        agent_id=agent_id,
                        tool_name=tool_name,
                        status=status,
                        input_params=kwargs or (
                            {f"arg{i}": a for i, a in enumerate(args)}
                            if args else None
                        ),
                        output_result=result,
                        duration_ms=elapsed_ms,
                    )

            return original_decorator(wrapper)

        return decorator

    def _log(self, agent_id, tool_name, status, input_params, output_result, duration_ms):
        """Write a tool_call record. Never raises — logging failure must not block tools."""
        try:
            if not agent_id:
                return
            conn = self._db.get_write_connection(agent_id)
            conn.execute(
                "INSERT INTO tool_calls (tool_name, status, input_summary, output_summary, "
                "duration_ms, source) VALUES (?, ?, ?, ?, ?, 'auto')",
                (
                    tool_name,
                    status,
                    _summarize_input(input_params if isinstance(input_params, dict) else None),
                    _truncate(
                        json.dumps(output_result, ensure_ascii=False, default=str)
                        if output_result is not None else None,
                        500,
                    ),
                    duration_ms,
                ),
            )
            conn.commit()
        except Exception:
            pass  # Never block tool execution
