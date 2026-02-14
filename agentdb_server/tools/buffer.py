"""Buffer (long document) management tools."""

from agentdb_server.db import DatabaseManager


def register(mcp, db: DatabaseManager):
    @mcp.tool()
    def store_buffer(agent_id: str, title: str, content: str) -> dict:
        """Store a buffer (long document) for the agent.

        Buffers are not loaded during awakening. Only their titles are
        listed in buffer_refs. Use load_buffer to retrieve full content.

        Args:
            agent_id: Agent identifier.
            title: Document title.
            content: Full document content.
        """
        conn = db.get_write_connection(agent_id)
        cursor = conn.execute(
            "INSERT INTO buffers (title, content) VALUES (?, ?)",
            (title, content),
        )
        conn.commit()
        return {"buffer_id": cursor.lastrowid}

    @mcp.tool()
    def load_buffer(agent_id: str, buffer_id: int) -> dict:
        """Load full buffer content.

        Args:
            agent_id: Agent identifier.
            buffer_id: Buffer ID.
        """
        conn = db.get_write_connection(agent_id)
        row = conn.execute(
            "SELECT id, title, content, summary, created_at "
            "FROM buffers WHERE id = ?",
            (buffer_id,),
        ).fetchone()
        if not row:
            return {"error": f"Buffer {buffer_id} not found"}
        return dict(row)

    @mcp.tool()
    def list_buffers(agent_id: str) -> list:
        """List buffers (id + title only, no content).

        Args:
            agent_id: Agent identifier.
        """
        conn = db.get_write_connection(agent_id)
        rows = conn.execute(
            "SELECT id, title, created_at FROM buffers "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
