"""Skill management tools."""

from agentdb_server.db import DatabaseManager


def register(mcp, db: DatabaseManager):
    @mcp.tool()
    def add_skill(
        agent_id: str,
        category: str,
        name: str,
        description: str,
        full_doc: str = "",
    ) -> dict:
        """Add a skill to the agent's catalog.

        Args:
            agent_id: Agent identifier.
            category: Skill category (e.g. 'coding', 'research').
            name: Skill name.
            description: Short description (loaded during awakening).
            full_doc: Full documentation (loaded on demand via load_skill).
        """
        conn = db.get_write_connection(agent_id)
        cursor = conn.execute(
            "INSERT INTO skills (category, name, description, full_doc) "
            "VALUES (?, ?, ?, ?)",
            (category, name, description, full_doc),
        )
        conn.commit()
        return {"skill_id": cursor.lastrowid}

    @mcp.tool()
    def get_skill_catalog(agent_id: str) -> dict:
        """Get the skill catalog (metadata only, grouped by category).

        Full documentation is not included. Use load_skill to get full_doc.

        Args:
            agent_id: Agent identifier.
        """
        conn = db.get_write_connection(agent_id)
        rows = conn.execute(
            "SELECT id, category, name, description FROM skills "
            "ORDER BY category, name"
        ).fetchall()
        catalog: dict[str, list] = {}
        for r in rows:
            d = dict(r)
            cat = d["category"]
            if cat not in catalog:
                catalog[cat] = []
            catalog[cat].append({
                "id": d["id"],
                "name": d["name"],
                "description": d["description"],
            })
        return catalog

    @mcp.tool()
    def load_skill(agent_id: str, skill_id: int) -> dict:
        """Load full skill details including full_doc.

        Args:
            agent_id: Agent identifier.
            skill_id: Skill ID.
        """
        conn = db.get_write_connection(agent_id)
        row = conn.execute(
            "SELECT id, category, name, description, full_doc, created_at "
            "FROM skills WHERE id = ?",
            (skill_id,),
        ).fetchone()
        if not row:
            return {"error": f"Skill {skill_id} not found"}
        return dict(row)
