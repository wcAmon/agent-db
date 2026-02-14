"""Awakening and system prompt management tools."""

import json

from agentdb_server.db import DatabaseManager


def register(mcp, db: DatabaseManager):
    @mcp.tool()
    def awaken(agent_id: str, include_tool_history: bool = False) -> dict:
        """Load layered memory for agent awakening.

        Returns up to 6-layer context:
          Layer 1: system_prompt    (~500 tokens)  - behavioral guidelines
          Layer 2: todos            (~200 tokens)  - pending tasks
          Layer 3: skills_catalog   (~1000 tokens) - skill metadata
          Layer 4: memories         (~3000 tokens) - core notes
          Layer 5: buffer_refs      (index only)   - document references
          Layer 6: tool_history     (optional)     - recent tool calls

        Args:
            agent_id: The agent's identifier.
            include_tool_history: If True, include recent 20 tool call summaries.

        Total: ~5K tokens (vs 50K+ full load).
        """
        conn = db.get_write_connection(agent_id)

        # Layer 1: Active system prompt
        row = conn.execute(
            "SELECT id, content, version FROM system_prompts "
            "WHERE is_active = 1 ORDER BY version DESC LIMIT 1"
        ).fetchone()
        system_prompt = dict(row) if row else None

        # Layer 2: Pending todos by priority (limit 5)
        rows = conn.execute(
            "SELECT id, content, priority, status FROM todos "
            "WHERE status = 'pending' ORDER BY priority DESC LIMIT 5"
        ).fetchall()
        todos = [dict(r) for r in rows]

        # Layer 3: Skills catalog (metadata only, grouped by category)
        rows = conn.execute(
            "SELECT id, category, name, description FROM skills "
            "ORDER BY category, name"
        ).fetchall()
        skills_catalog: dict[str, list] = {}
        for r in rows:
            d = dict(r)
            cat = d["category"]
            if cat not in skills_catalog:
                skills_catalog[cat] = []
            skills_catalog[cat].append({
                "id": d["id"],
                "name": d["name"],
                "description": d["description"],
            })

        # Layer 4: Top memories by importance (limit 10)
        rows = conn.execute(
            "SELECT id, title, content, importance, mem_type FROM memories "
            "ORDER BY importance DESC LIMIT 10"
        ).fetchall()
        memories = [dict(r) for r in rows]

        # Layer 5: Buffer references (id + title only, no content)
        rows = conn.execute(
            "SELECT id, title FROM buffers ORDER BY created_at DESC"
        ).fetchall()
        buffer_refs = [dict(r) for r in rows]

        # Layer 6: Tool call history (optional)
        tool_history = []
        if include_tool_history:
            rows = conn.execute(
                "SELECT id, tool_name, status, created_at FROM tool_calls "
                "ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            tool_history = [dict(r) for r in rows]

        # Build context
        context = {
            "agent_id": agent_id,
            "system_prompt": system_prompt,
            "todos": todos,
            "skills_catalog": skills_catalog,
            "memories": memories,
            "buffer_refs": buffer_refs,
        }
        if include_tool_history:
            context["tool_history"] = tool_history

        # Estimate tokens (~4 chars per token)
        total_chars = len(json.dumps(context, ensure_ascii=False))
        total_tokens = total_chars // 4

        # Record awakening
        all_skill_ids = [
            s["id"]
            for cat_skills in skills_catalog.values()
            for s in cat_skills
        ]
        conn.execute(
            "INSERT INTO awakenings "
            "(loaded_system_prompt_version, loaded_todos, loaded_skills, "
            "loaded_memories, loaded_buffers, loaded_tool_calls, total_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                system_prompt["version"] if system_prompt else None,
                json.dumps([t["id"] for t in todos]),
                json.dumps(all_skill_ids),
                json.dumps([m["id"] for m in memories]),
                json.dumps([b["id"] for b in buffer_refs]),
                json.dumps([t["id"] for t in tool_history]) if tool_history else None,
                total_tokens,
            ),
        )
        conn.commit()

        context["awakening_id"] = conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]
        context["total_tokens"] = total_tokens

        return context

    @mcp.tool()
    def update_system_prompt(agent_id: str, content: str) -> dict:
        """Update the agent's system prompt. Creates a new version;
        old versions are automatically marked inactive."""
        conn = db.get_write_connection(agent_id)

        # Get current max version
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) as max_ver FROM system_prompts"
        ).fetchone()
        new_version = row["max_ver"] + 1

        # Deactivate all existing versions
        conn.execute(
            "UPDATE system_prompts SET is_active = 0, "
            "updated_at = CURRENT_TIMESTAMP"
        )

        # Insert new version
        conn.execute(
            "INSERT INTO system_prompts (content, version, is_active) "
            "VALUES (?, ?, 1)",
            (content, new_version),
        )
        conn.commit()

        return {"version": new_version}

    @mcp.tool()
    def get_system_prompt(agent_id: str) -> dict:
        """Get the current active system prompt for an agent."""
        conn = db.get_write_connection(agent_id)
        row = conn.execute(
            "SELECT id, content, version, created_at FROM system_prompts "
            "WHERE is_active = 1 ORDER BY version DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {"error": "No system prompt set"}
        return dict(row)
