"""Dashboard REST API — Flask Blueprint.

Provides admin-level CRUD endpoints for all agent resources.
Intended for CLI tools and programmatic access.
"""

import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, request, abort
from sqlalchemy import case, func, Integer

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

api_bp = Blueprint("api", __name__, url_prefix="/api")
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


def _get_json() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        abort(400, description="Request body must be JSON")
    return data


# ── Agents ──────────────────────────────────────────────────────────


@api_bp.route("/agents", methods=["GET"])
def list_agents():
    agents = []
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
                "last_awakening": str(last.created_at) if last else None,
            })
        finally:
            session.close()
    return jsonify(agents)


# ── Memories ────────────────────────────────────────────────────────


@api_bp.route("/agents/<agent_id>/memories", methods=["GET"])
def list_memories(agent_id):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = (
            session.query(Memory)
            .order_by(Memory.importance.desc())
            .all()
        )
        return jsonify([{
            "id": m.id, "title": m.title, "content": m.content,
            "importance": m.importance, "mem_type": m.mem_type,
            "created_at": str(m.created_at), "updated_at": str(m.updated_at),
        } for m in rows])
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/memories/<int:mid>", methods=["GET"])
def get_memory(agent_id, mid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        m = session.query(Memory).get(mid)
        if not m:
            abort(404, description="Memory not found")
        return jsonify({
            "id": m.id, "title": m.title, "content": m.content,
            "importance": m.importance, "mem_type": m.mem_type,
            "created_at": str(m.created_at), "updated_at": str(m.updated_at),
        })
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/memories", methods=["POST"])
def create_memory(agent_id):
    db_path = _agent_db_path(agent_id)
    data = _get_json()
    if not data.get("title") or not data.get("content"):
        abort(400, description="'title' and 'content' are required")
    session = get_session(str(db_path))
    try:
        m = Memory(
            title=data["title"],
            content=data["content"],
            importance=data.get("importance", 0.5),
            mem_type=data.get("mem_type", "fact"),
        )
        session.add(m)
        session.commit()
        return jsonify({"id": m.id, "title": m.title}), 201
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/memories/<int:mid>", methods=["PUT"])
def update_memory(agent_id, mid):
    db_path = _agent_db_path(agent_id)
    data = _get_json()
    session = get_session(str(db_path))
    try:
        m = session.query(Memory).get(mid)
        if not m:
            abort(404, description="Memory not found")
        for field in ("title", "content", "importance", "mem_type"):
            if field in data:
                setattr(m, field, data[field])
        session.commit()
        return jsonify({"id": m.id, "title": m.title})
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/memories/<int:mid>", methods=["DELETE"])
def delete_memory(agent_id, mid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        m = session.query(Memory).get(mid)
        if not m:
            abort(404, description="Memory not found")
        session.delete(m)
        session.commit()
        return jsonify({"deleted": mid})
    finally:
        session.close()


# ── Todos ───────────────────────────────────────────────────────────


@api_bp.route("/agents/<agent_id>/todos", methods=["GET"])
def list_todos(agent_id):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        status_filter = request.args.get("status")
        q = session.query(Todo)
        if status_filter:
            q = q.filter(Todo.status == status_filter)
        rows = q.order_by(Todo.priority.desc()).all()
        return jsonify([{
            "id": t.id, "content": t.content, "priority": t.priority,
            "status": t.status, "created_at": str(t.created_at),
            "updated_at": str(t.updated_at),
        } for t in rows])
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/todos/<int:tid>", methods=["GET"])
def get_todo(agent_id, tid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        t = session.query(Todo).get(tid)
        if not t:
            abort(404, description="Todo not found")
        return jsonify({
            "id": t.id, "content": t.content, "priority": t.priority,
            "status": t.status, "created_at": str(t.created_at),
            "updated_at": str(t.updated_at),
        })
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/todos", methods=["POST"])
def create_todo(agent_id):
    db_path = _agent_db_path(agent_id)
    data = _get_json()
    if not data.get("content"):
        abort(400, description="'content' is required")
    session = get_session(str(db_path))
    try:
        t = Todo(
            content=data["content"],
            priority=max(1, min(10, data.get("priority", 5))),
            status=data.get("status", "pending"),
        )
        session.add(t)
        session.commit()
        return jsonify({"id": t.id, "content": t.content}), 201
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/todos/<int:tid>", methods=["PUT"])
def update_todo(agent_id, tid):
    db_path = _agent_db_path(agent_id)
    data = _get_json()
    session = get_session(str(db_path))
    try:
        t = session.query(Todo).get(tid)
        if not t:
            abort(404, description="Todo not found")
        for field in ("content", "priority", "status"):
            if field in data:
                setattr(t, field, data[field])
        session.commit()
        return jsonify({"id": t.id, "content": t.content})
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/todos/<int:tid>", methods=["DELETE"])
def delete_todo(agent_id, tid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        t = session.query(Todo).get(tid)
        if not t:
            abort(404, description="Todo not found")
        session.delete(t)
        session.commit()
        return jsonify({"deleted": tid})
    finally:
        session.close()


# ── Skills ──────────────────────────────────────────────────────────


@api_bp.route("/agents/<agent_id>/skills", methods=["GET"])
def list_skills(agent_id):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = session.query(Skill).order_by(Skill.category, Skill.name).all()
        return jsonify([{
            "id": s.id, "category": s.category, "name": s.name,
            "description": s.description,
            "created_at": str(s.created_at), "updated_at": str(s.updated_at),
        } for s in rows])
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/skills/<int:sid>", methods=["GET"])
def get_skill(agent_id, sid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        s = session.query(Skill).get(sid)
        if not s:
            abort(404, description="Skill not found")
        return jsonify({
            "id": s.id, "category": s.category, "name": s.name,
            "description": s.description, "full_doc": s.full_doc,
            "created_at": str(s.created_at), "updated_at": str(s.updated_at),
        })
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/skills", methods=["POST"])
def create_skill(agent_id):
    db_path = _agent_db_path(agent_id)
    data = _get_json()
    for field in ("category", "name", "description"):
        if not data.get(field):
            abort(400, description=f"'{field}' is required")
    session = get_session(str(db_path))
    try:
        s = Skill(
            category=data["category"],
            name=data["name"],
            description=data["description"],
            full_doc=data.get("full_doc", ""),
        )
        session.add(s)
        session.commit()
        return jsonify({"id": s.id, "name": s.name}), 201
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/skills/<int:sid>", methods=["PUT"])
def update_skill(agent_id, sid):
    db_path = _agent_db_path(agent_id)
    data = _get_json()
    session = get_session(str(db_path))
    try:
        s = session.query(Skill).get(sid)
        if not s:
            abort(404, description="Skill not found")
        for field in ("category", "name", "description", "full_doc"):
            if field in data:
                setattr(s, field, data[field])
        session.commit()
        return jsonify({"id": s.id, "name": s.name})
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/skills/<int:sid>", methods=["DELETE"])
def delete_skill(agent_id, sid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        s = session.query(Skill).get(sid)
        if not s:
            abort(404, description="Skill not found")
        session.delete(s)
        session.commit()
        return jsonify({"deleted": sid})
    finally:
        session.close()


# ── Buffers ─────────────────────────────────────────────────────────


@api_bp.route("/agents/<agent_id>/buffers", methods=["GET"])
def list_buffers(agent_id):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = session.query(Buffer).order_by(Buffer.created_at.desc()).all()
        return jsonify([{
            "id": b.id, "title": b.title, "summary": b.summary,
            "created_at": str(b.created_at),
        } for b in rows])
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/buffers/<int:bid>", methods=["GET"])
def get_buffer(agent_id, bid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        b = session.query(Buffer).get(bid)
        if not b:
            abort(404, description="Buffer not found")
        return jsonify({
            "id": b.id, "title": b.title, "content": b.content,
            "summary": b.summary, "created_at": str(b.created_at),
        })
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/buffers", methods=["POST"])
def create_buffer(agent_id):
    db_path = _agent_db_path(agent_id)
    data = _get_json()
    if not data.get("title") or not data.get("content"):
        abort(400, description="'title' and 'content' are required")
    session = get_session(str(db_path))
    try:
        b = Buffer(
            title=data["title"],
            content=data["content"],
            summary=data.get("summary"),
        )
        session.add(b)
        session.commit()
        return jsonify({"id": b.id, "title": b.title}), 201
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/buffers/<int:bid>", methods=["PUT"])
def update_buffer(agent_id, bid):
    db_path = _agent_db_path(agent_id)
    data = _get_json()
    session = get_session(str(db_path))
    try:
        b = session.query(Buffer).get(bid)
        if not b:
            abort(404, description="Buffer not found")
        for field in ("title", "content", "summary"):
            if field in data:
                setattr(b, field, data[field])
        session.commit()
        return jsonify({"id": b.id, "title": b.title})
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/buffers/<int:bid>", methods=["DELETE"])
def delete_buffer(agent_id, bid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        b = session.query(Buffer).get(bid)
        if not b:
            abort(404, description="Buffer not found")
        session.delete(b)
        session.commit()
        return jsonify({"deleted": bid})
    finally:
        session.close()


# ── System Prompts ──────────────────────────────────────────────────


@api_bp.route("/agents/<agent_id>/system_prompts", methods=["GET"])
def list_system_prompts(agent_id):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = (
            session.query(SystemPrompt)
            .order_by(SystemPrompt.version.desc())
            .all()
        )
        return jsonify([{
            "id": sp.id, "version": sp.version, "is_active": sp.is_active,
            "content": sp.content,
            "created_at": str(sp.created_at), "updated_at": str(sp.updated_at),
        } for sp in rows])
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/system_prompts/<int:spid>", methods=["GET"])
def get_system_prompt(agent_id, spid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        sp = session.query(SystemPrompt).get(spid)
        if not sp:
            abort(404, description="System prompt not found")
        return jsonify({
            "id": sp.id, "version": sp.version, "is_active": sp.is_active,
            "content": sp.content,
            "created_at": str(sp.created_at), "updated_at": str(sp.updated_at),
        })
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/system_prompts", methods=["POST"])
def create_system_prompt(agent_id):
    db_path = _agent_db_path(agent_id)
    data = _get_json()
    if not data.get("content"):
        abort(400, description="'content' is required")
    session = get_session(str(db_path))
    try:
        # Get current max version
        max_ver = session.query(func.max(SystemPrompt.version)).scalar() or 0
        # Deactivate all
        session.query(SystemPrompt).update({SystemPrompt.is_active: False})
        sp = SystemPrompt(
            content=data["content"],
            version=max_ver + 1,
            is_active=True,
        )
        session.add(sp)
        session.commit()
        return jsonify({"id": sp.id, "version": sp.version}), 201
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/system_prompts/<int:spid>", methods=["PUT"])
def update_system_prompt(agent_id, spid):
    db_path = _agent_db_path(agent_id)
    data = _get_json()
    session = get_session(str(db_path))
    try:
        sp = session.query(SystemPrompt).get(spid)
        if not sp:
            abort(404, description="System prompt not found")
        if "content" in data:
            sp.content = data["content"]
        if "is_active" in data:
            if data["is_active"]:
                session.query(SystemPrompt).update({SystemPrompt.is_active: False})
            sp.is_active = data["is_active"]
        session.commit()
        return jsonify({"id": sp.id, "version": sp.version})
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/system_prompts/<int:spid>", methods=["DELETE"])
def delete_system_prompt(agent_id, spid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        sp = session.query(SystemPrompt).get(spid)
        if not sp:
            abort(404, description="System prompt not found")
        session.delete(sp)
        session.commit()
        return jsonify({"deleted": spid})
    finally:
        session.close()


# ── Tool Calls ──────────────────────────────────────────────────────


@api_bp.route("/agents/<agent_id>/tool_calls", methods=["GET"])
def list_tool_calls(agent_id):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        tool_name = request.args.get("tool_name")
        limit = min(int(request.args.get("limit", 50)), 200)
        q = session.query(ToolCall)
        if tool_name:
            q = q.filter(ToolCall.tool_name == tool_name)
        rows = q.order_by(ToolCall.created_at.desc()).limit(limit).all()
        return jsonify([{
            "id": tc.id, "tool_name": tc.tool_name, "status": tc.status,
            "input_summary": tc.input_summary, "output_summary": tc.output_summary,
            "duration_ms": tc.duration_ms, "source": tc.source,
            "created_at": str(tc.created_at),
        } for tc in rows])
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/tool_calls/stats", methods=["GET"])
def tool_call_stats(agent_id):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = (
            session.query(
                ToolCall.tool_name,
                func.count(ToolCall.id).label("total_calls"),
                func.sum(
                    case((ToolCall.status == "success", 1), else_=0)
                ).label("success_count"),
                func.sum(
                    case((ToolCall.status == "error", 1), else_=0)
                ).label("error_count"),
                func.avg(ToolCall.duration_ms).label("avg_duration_ms"),
            )
            .group_by(ToolCall.tool_name)
            .order_by(func.count(ToolCall.id).desc())
            .all()
        )
        return jsonify([{
            "tool_name": r.tool_name,
            "total_calls": r.total_calls,
            "success_count": r.success_count or 0,
            "error_count": r.error_count or 0,
            "avg_duration_ms": round(r.avg_duration_ms, 1) if r.avg_duration_ms else 0,
        } for r in rows])
    finally:
        session.close()


# ── Awakenings ──────────────────────────────────────────────────────


@api_bp.route("/agents/<agent_id>/awakenings", methods=["GET"])
def list_awakenings(agent_id):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = (
            session.query(Awakening)
            .order_by(Awakening.created_at.desc())
            .limit(50)
            .all()
        )
        return jsonify([{
            "id": aw.id,
            "loaded_system_prompt_version": aw.loaded_system_prompt_version,
            "total_tokens": aw.total_tokens,
            "created_at": str(aw.created_at),
        } for aw in rows])
    finally:
        session.close()


@api_bp.route("/agents/<agent_id>/awakenings/<int:aid>", methods=["GET"])
def get_awakening(agent_id, aid):
    db_path = _agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        aw = session.query(Awakening).get(aid)
        if not aw:
            abort(404, description="Awakening not found")
        return jsonify({
            "id": aw.id,
            "loaded_system_prompt_version": aw.loaded_system_prompt_version,
            "loaded_todos": json.loads(aw.loaded_todos) if aw.loaded_todos else [],
            "loaded_skills": json.loads(aw.loaded_skills) if aw.loaded_skills else [],
            "loaded_memories": json.loads(aw.loaded_memories) if aw.loaded_memories else [],
            "loaded_buffers": json.loads(aw.loaded_buffers) if aw.loaded_buffers else [],
            "loaded_tool_calls": json.loads(aw.loaded_tool_calls) if aw.loaded_tool_calls else [],
            "total_tokens": aw.total_tokens,
            "created_at": str(aw.created_at),
        })
    finally:
        session.close()


# ── Error Handlers ──────────────────────────────────────────────────


@api_bp.errorhandler(400)
def bad_request(e):
    return jsonify({"error": str(e.description)}), 400


@api_bp.errorhandler(404)
def not_found(e):
    return jsonify({"error": str(e.description)}), 404
