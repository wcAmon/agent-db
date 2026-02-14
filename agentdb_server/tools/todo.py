"""Todo management tools."""

from agentdb_server.db import DatabaseManager


def register(mcp, db: DatabaseManager):
    @mcp.tool()
    def add_todo(agent_id: str, content: str, priority: int = 5) -> dict:
        """Add a todo item for the agent.

        Args:
            agent_id: Agent identifier.
            content: Todo description.
            priority: 1-10 (10 = highest priority).
        """
        conn = db.get_write_connection(agent_id)
        cursor = conn.execute(
            "INSERT INTO todos (content, priority) VALUES (?, ?)",
            (content, min(max(priority, 1), 10)),
        )
        conn.commit()
        return {"todo_id": cursor.lastrowid}

    @mcp.tool()
    def list_todos(agent_id: str, status: str = "") -> list:
        """List agent's todos. Optionally filter by status.

        Args:
            agent_id: Agent identifier.
            status: Filter by 'pending', 'in_progress', or 'done'. Empty = all.
        """
        conn = db.get_write_connection(agent_id)
        if status:
            rows = conn.execute(
                "SELECT id, content, priority, status, created_at "
                "FROM todos WHERE status = ? ORDER BY priority DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, content, priority, status, created_at "
                "FROM todos ORDER BY priority DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    @mcp.tool()
    def complete_todo(agent_id: str, todo_id: int) -> dict:
        """Mark a todo as done.

        Args:
            agent_id: Agent identifier.
            todo_id: ID of the todo to complete.
        """
        conn = db.get_write_connection(agent_id)
        cursor = conn.execute(
            "UPDATE todos SET status = 'done', updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (todo_id,),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return {"error": f"Todo {todo_id} not found"}
        return {"success": True, "todo_id": todo_id}
