"""AgentDB Dashboard - Flask application.

Reads SQLite databases directly via SQLAlchemy ORM.
No dependency on the MCP Server at runtime.

Usage:
    python -m dashboard.app
    # or via entry point:
    agentdb-dashboard

Environment variables:
    AGENTDB_AGENTS_DIR  Path to agents database directory (default: ./agents)
"""

import json
import os
from pathlib import Path

from flask import Flask, render_template, abort
from sqlalchemy import func

from .models import (
    get_session,
    Awakening,
    Buffer,
    Memory,
    Skill,
    SystemPrompt,
    Todo,
    ToolCall,
)
from .api import api_bp

app = Flask(__name__)
app.register_blueprint(api_bp)
AGENTS_DIR = Path(os.environ.get("AGENTDB_AGENTS_DIR", "agents"))


def _list_agent_ids() -> list[str]:
    if not AGENTS_DIR.exists():
        return []
    return sorted(p.stem for p in AGENTS_DIR.glob("*.db"))


def _agent_db_path(agent_id: str) -> Path:
    path = AGENTS_DIR / f"{agent_id}.db"
    if not path.exists():
        abort(404, description=f"Agent '{agent_id}' not found")
    return path


# ── Routes ──────────────────────────────────────────────────────────


@app.route("/")
def index():
    """Home page: list all agents with summary stats."""
    agents = []
    for agent_id in _list_agent_ids():
        db_path = AGENTS_DIR / f"{agent_id}.db"
        session = get_session(str(db_path))
        try:
            last = (
                session.query(Awakening)
                .order_by(Awakening.created_at.desc())
                .first()
            )
            pending_count = (
                session.query(func.count(Todo.id))
                .filter(Todo.status == "pending")
                .scalar()
            )
            memory_count = session.query(func.count(Memory.id)).scalar()
            agents.append({
                "id": agent_id,
                "last_awakening": last.created_at if last else None,
                "pending_todos": pending_count,
                "memory_count": memory_count,
            })
        finally:
            session.close()
    return render_template("index.html", agents=agents)


@app.route("/agent/<agent_id>")
def agent_detail(agent_id: str):
    """Agent detail page: system prompt, todos, memories, skills, buffers."""
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        # System prompt
        prompt = (
            session.query(SystemPrompt)
            .filter(SystemPrompt.is_active == True)  # noqa: E712
            .order_by(SystemPrompt.version.desc())
            .first()
        )

        # Pending todos
        todos = (
            session.query(Todo)
            .filter(Todo.status == "pending")
            .order_by(Todo.priority.desc())
            .all()
        )

        # Top memories
        memories = (
            session.query(Memory)
            .order_by(Memory.importance.desc())
            .limit(20)
            .all()
        )

        # Skills by category
        skills = (
            session.query(Skill)
            .order_by(Skill.category, Skill.name)
            .all()
        )
        skill_categories: dict[str, list] = {}
        for s in skills:
            if s.category not in skill_categories:
                skill_categories[s.category] = []
            skill_categories[s.category].append(s)

        # Buffers
        buffers = (
            session.query(Buffer)
            .order_by(Buffer.created_at.desc())
            .all()
        )

        # Recent tool calls
        tool_calls = (
            session.query(ToolCall)
            .order_by(ToolCall.created_at.desc())
            .limit(20)
            .all()
        )

        # Recent awakenings
        awakenings = (
            session.query(Awakening)
            .order_by(Awakening.created_at.desc())
            .limit(20)
            .all()
        )

        return render_template(
            "agent_detail.html",
            agent_id=agent_id,
            prompt=prompt,
            todos=todos,
            memories=memories,
            skill_categories=skill_categories,
            buffers=buffers,
            tool_calls=tool_calls,
            awakenings=awakenings,
        )
    finally:
        session.close()


@app.route("/admin")
def admin():
    """Admin overview: all agents with stats and recent tool activity."""
    agents = []
    recent_tool_activity = []
    for agent_id in _list_agent_ids():
        db_path = AGENTS_DIR / f"{agent_id}.db"
        session = get_session(str(db_path))
        try:
            pending_count = (
                session.query(func.count(Todo.id))
                .filter(Todo.status == "pending")
                .scalar()
            )
            memory_count = session.query(func.count(Memory.id)).scalar()
            tool_call_count = session.query(func.count(ToolCall.id)).scalar()
            last = (
                session.query(Awakening)
                .order_by(Awakening.created_at.desc())
                .first()
            )
            agents.append({
                "id": agent_id,
                "pending_todos": pending_count,
                "memory_count": memory_count,
                "tool_call_count": tool_call_count,
                "last_awakening": last.created_at if last else None,
            })

            # Recent tool calls for timeline
            recent_tcs = (
                session.query(ToolCall)
                .order_by(ToolCall.created_at.desc())
                .limit(10)
                .all()
            )
            for tc in recent_tcs:
                recent_tool_activity.append({
                    "agent_id": agent_id,
                    "tool_name": tc.tool_name,
                    "status": tc.status,
                    "source": tc.source,
                    "duration_ms": tc.duration_ms,
                    "created_at": tc.created_at,
                })
        finally:
            session.close()

    # Sort timeline by created_at descending
    recent_tool_activity.sort(key=lambda x: str(x["created_at"] or ""), reverse=True)
    recent_tool_activity = recent_tool_activity[:30]

    return render_template(
        "admin.html",
        agents=agents,
        recent_tool_activity=recent_tool_activity,
    )


@app.route("/agent/<agent_id>/awakening/<int:awakening_id>")
def awakening_detail(agent_id: str, awakening_id: int):
    """Awakening detail page: snapshot of what was loaded."""
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        aw = session.query(Awakening).get(awakening_id)
        if not aw:
            abort(404, description="Awakening not found")

        # Parse JSON arrays of loaded IDs
        todo_ids = json.loads(aw.loaded_todos) if aw.loaded_todos else []
        skill_ids = json.loads(aw.loaded_skills) if aw.loaded_skills else []
        memory_ids = json.loads(aw.loaded_memories) if aw.loaded_memories else []
        buffer_ids = json.loads(aw.loaded_buffers) if aw.loaded_buffers else []

        todos = session.query(Todo).filter(Todo.id.in_(todo_ids)).all() if todo_ids else []
        skills = session.query(Skill).filter(Skill.id.in_(skill_ids)).all() if skill_ids else []
        memories = session.query(Memory).filter(Memory.id.in_(memory_ids)).all() if memory_ids else []
        buffers = session.query(Buffer).filter(Buffer.id.in_(buffer_ids)).all() if buffer_ids else []

        # System prompt at that version
        prompt = None
        if aw.loaded_system_prompt_version:
            prompt = (
                session.query(SystemPrompt)
                .filter(SystemPrompt.version == aw.loaded_system_prompt_version)
                .first()
            )

        return render_template(
            "awakening_detail.html",
            agent_id=agent_id,
            awakening=aw,
            prompt=prompt,
            todos=todos,
            skills=skills,
            memories=memories,
            buffers=buffers,
        )
    finally:
        session.close()


def main():
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()
