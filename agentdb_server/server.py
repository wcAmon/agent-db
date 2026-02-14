"""AgentDB MCP Server - main entry point.

Usage:
    python -m agentdb_server.server
    # or via entry point:
    agentdb-server

Environment variables:
    AGENTDB_AGENTS_DIR  Path to agents database directory (default: ./agents)
"""

import atexit
import os

from mcp.server.mcpserver import MCPServer

from .db import DatabaseManager
from .tool_logger import AutoLoggingMCP
from .tools import awaken, todo, memory, skill, buffer, tool_call


def create_server() -> tuple[MCPServer, DatabaseManager]:
    agents_dir = os.environ.get("AGENTDB_AGENTS_DIR", "agents")
    db = DatabaseManager(agents_dir)

    mcp = MCPServer(
        name="AgentDB",
        instructions=(
            "Agent memory management system with layered awakening. "
            "Use 'awaken' to load an agent's context, then manage "
            "todos, memories, skills, and buffers."
        ),
        version="0.1.0",
    )

    # Auto-logged proxy — excludes tool_call tools to avoid recursion
    logged_mcp = AutoLoggingMCP(mcp, db, exclude={
        "log_tool_call", "list_tool_calls", "get_tool_stats",
    })

    # Register auto-logged tool modules
    awaken.register(logged_mcp, db)
    todo.register(logged_mcp, db)
    memory.register(logged_mcp, db)
    skill.register(logged_mcp, db)
    buffer.register(logged_mcp, db)

    # Register tool_call module without auto-logging (uses raw mcp)
    tool_call.register(mcp, db)

    return mcp, db


mcp, _db = create_server()
atexit.register(_db.close_all)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
