"""Memory management tools."""

from agentdb_server.db import DatabaseManager


def register(mcp, db: DatabaseManager):
    @mcp.tool()
    def remember(
        agent_id: str,
        title: str,
        content: str,
        importance: float = 0.5,
        mem_type: str = "fact",
    ) -> dict:
        """Store a memory note for the agent.

        Args:
            agent_id: Agent identifier.
            title: Short title for the memory.
            content: Full content of the memory.
            importance: 0.0-1.0 (1.0 = most important).
            mem_type: 'fact', 'experience', or 'insight'.
        """
        conn = db.get_write_connection(agent_id)
        importance = min(max(importance, 0.0), 1.0)
        if mem_type not in ("fact", "experience", "insight"):
            mem_type = "fact"
        cursor = conn.execute(
            "INSERT INTO memories (title, content, importance, mem_type) "
            "VALUES (?, ?, ?, ?)",
            (title, content, importance, mem_type),
        )
        conn.commit()
        return {"memory_id": cursor.lastrowid}

    @mcp.tool()
    def search_memories(agent_id: str, query: str, limit: int = 5) -> list:
        """Search memories by keyword (LIKE search).

        Args:
            agent_id: Agent identifier.
            query: Search keyword.
            limit: Max results (default 5).
        """
        conn = db.get_write_connection(agent_id)
        rows = conn.execute(
            "SELECT id, title, content, importance, mem_type, created_at "
            "FROM memories "
            "WHERE title LIKE ? OR content LIKE ? "
            "ORDER BY importance DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    @mcp.tool()
    def get_memory(agent_id: str, memory_id: int) -> dict:
        """Get a specific memory by ID.

        Args:
            agent_id: Agent identifier.
            memory_id: Memory ID.
        """
        conn = db.get_write_connection(agent_id)
        row = conn.execute(
            "SELECT id, title, content, importance, mem_type, "
            "created_at, updated_at FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        if not row:
            return {"error": f"Memory {memory_id} not found"}
        return dict(row)
