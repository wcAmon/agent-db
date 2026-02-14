"""Dashboard REST API — FastAPI Router.

Provides admin-level CRUD endpoints for all agent resources.
Intended for CLI tools and programmatic access.
"""

import json

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import case, func

from .dependencies import list_agent_ids, get_agents_dir, get_agent_db_path
from .models import (
    get_session,
    AgentScheduleConfig,
    Awakening,
    Buffer,
    McpServer,
    Memory,
    ScheduledRun,
    Skill,
    SystemPrompt,
    Todo,
    ToolCall,
)
from .schemas import (
    BufferCreate,
    BufferUpdate,
    McpServerCreate,
    McpServerUpdate,
    MemoryCreate,
    MemoryUpdate,
    ScheduleConfigUpdate,
    SkillCreate,
    SkillUpdate,
    SystemPromptCreate,
    SystemPromptUpdate,
    TodoCreate,
    TodoUpdate,
)

router = APIRouter()


# ── Agents ──────────────────────────────────────────────────────────


@router.get("/agents")
def api_list_agents():
    agents = []
    agents_dir = get_agents_dir()
    for agent_id in list_agent_ids():
        db_path = agents_dir / f"{agent_id}.db"
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
    return agents


# ── Memories ────────────────────────────────────────────────────────


@router.get("/agents/{agent_id}/memories")
def api_list_memories(agent_id: str):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = (
            session.query(Memory)
            .order_by(Memory.importance.desc())
            .all()
        )
        return [{
            "id": m.id, "title": m.title, "content": m.content,
            "importance": m.importance, "mem_type": m.mem_type,
            "created_at": str(m.created_at), "updated_at": str(m.updated_at),
        } for m in rows]
    finally:
        session.close()


@router.get("/agents/{agent_id}/memories/{mid}")
def api_get_memory(agent_id: str, mid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        m = session.query(Memory).get(mid)
        if not m:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {
            "id": m.id, "title": m.title, "content": m.content,
            "importance": m.importance, "mem_type": m.mem_type,
            "created_at": str(m.created_at), "updated_at": str(m.updated_at),
        }
    finally:
        session.close()


@router.post("/agents/{agent_id}/memories", status_code=201)
def api_create_memory(agent_id: str, data: MemoryCreate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        m = Memory(
            title=data.title,
            content=data.content,
            importance=data.importance,
            mem_type=data.mem_type,
        )
        session.add(m)
        session.commit()
        return {"id": m.id, "title": m.title}
    finally:
        session.close()


@router.put("/agents/{agent_id}/memories/{mid}")
def api_update_memory(agent_id: str, mid: int, data: MemoryUpdate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        m = session.query(Memory).get(mid)
        if not m:
            raise HTTPException(status_code=404, detail="Memory not found")
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(m, field, value)
        session.commit()
        return {"id": m.id, "title": m.title}
    finally:
        session.close()


@router.delete("/agents/{agent_id}/memories/{mid}")
def api_delete_memory(agent_id: str, mid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        m = session.query(Memory).get(mid)
        if not m:
            raise HTTPException(status_code=404, detail="Memory not found")
        session.delete(m)
        session.commit()
        return {"deleted": mid}
    finally:
        session.close()


# ── Todos ───────────────────────────────────────────────────────────


@router.get("/agents/{agent_id}/todos")
def api_list_todos(agent_id: str, status: str | None = None):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        q = session.query(Todo)
        if status:
            q = q.filter(Todo.status == status)
        rows = q.order_by(Todo.priority.desc()).all()
        return [{
            "id": t.id, "content": t.content, "priority": t.priority,
            "status": t.status, "created_at": str(t.created_at),
            "updated_at": str(t.updated_at),
        } for t in rows]
    finally:
        session.close()


@router.get("/agents/{agent_id}/todos/{tid}")
def api_get_todo(agent_id: str, tid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        t = session.query(Todo).get(tid)
        if not t:
            raise HTTPException(status_code=404, detail="Todo not found")
        return {
            "id": t.id, "content": t.content, "priority": t.priority,
            "status": t.status, "created_at": str(t.created_at),
            "updated_at": str(t.updated_at),
        }
    finally:
        session.close()


@router.post("/agents/{agent_id}/todos", status_code=201)
def api_create_todo(agent_id: str, data: TodoCreate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        t = Todo(
            content=data.content,
            priority=max(1, min(10, data.priority)),
            status=data.status,
        )
        session.add(t)
        session.commit()
        return {"id": t.id, "content": t.content}
    finally:
        session.close()


@router.put("/agents/{agent_id}/todos/{tid}")
def api_update_todo(agent_id: str, tid: int, data: TodoUpdate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        t = session.query(Todo).get(tid)
        if not t:
            raise HTTPException(status_code=404, detail="Todo not found")
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(t, field, value)
        session.commit()
        return {"id": t.id, "content": t.content}
    finally:
        session.close()


@router.delete("/agents/{agent_id}/todos/{tid}")
def api_delete_todo(agent_id: str, tid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        t = session.query(Todo).get(tid)
        if not t:
            raise HTTPException(status_code=404, detail="Todo not found")
        session.delete(t)
        session.commit()
        return {"deleted": tid}
    finally:
        session.close()


# ── Skills ──────────────────────────────────────────────────────────


@router.get("/agents/{agent_id}/skills")
def api_list_skills(agent_id: str):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = session.query(Skill).order_by(Skill.category, Skill.name).all()
        return [{
            "id": s.id, "category": s.category, "name": s.name,
            "description": s.description,
            "created_at": str(s.created_at), "updated_at": str(s.updated_at),
        } for s in rows]
    finally:
        session.close()


@router.get("/agents/{agent_id}/skills/{sid}")
def api_get_skill(agent_id: str, sid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        s = session.query(Skill).get(sid)
        if not s:
            raise HTTPException(status_code=404, detail="Skill not found")
        return {
            "id": s.id, "category": s.category, "name": s.name,
            "description": s.description, "full_doc": s.full_doc,
            "created_at": str(s.created_at), "updated_at": str(s.updated_at),
        }
    finally:
        session.close()


@router.post("/agents/{agent_id}/skills", status_code=201)
def api_create_skill(agent_id: str, data: SkillCreate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        s = Skill(
            category=data.category,
            name=data.name,
            description=data.description,
            full_doc=data.full_doc,
        )
        session.add(s)
        session.commit()
        return {"id": s.id, "name": s.name}
    finally:
        session.close()


@router.put("/agents/{agent_id}/skills/{sid}")
def api_update_skill(agent_id: str, sid: int, data: SkillUpdate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        s = session.query(Skill).get(sid)
        if not s:
            raise HTTPException(status_code=404, detail="Skill not found")
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(s, field, value)
        session.commit()
        return {"id": s.id, "name": s.name}
    finally:
        session.close()


@router.delete("/agents/{agent_id}/skills/{sid}")
def api_delete_skill(agent_id: str, sid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        s = session.query(Skill).get(sid)
        if not s:
            raise HTTPException(status_code=404, detail="Skill not found")
        session.delete(s)
        session.commit()
        return {"deleted": sid}
    finally:
        session.close()


# ── Buffers ─────────────────────────────────────────────────────────


@router.get("/agents/{agent_id}/buffers")
def api_list_buffers(agent_id: str):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = session.query(Buffer).order_by(Buffer.created_at.desc()).all()
        return [{
            "id": b.id, "title": b.title, "summary": b.summary,
            "created_at": str(b.created_at),
        } for b in rows]
    finally:
        session.close()


@router.get("/agents/{agent_id}/buffers/{bid}")
def api_get_buffer(agent_id: str, bid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        b = session.query(Buffer).get(bid)
        if not b:
            raise HTTPException(status_code=404, detail="Buffer not found")
        return {
            "id": b.id, "title": b.title, "content": b.content,
            "summary": b.summary, "created_at": str(b.created_at),
        }
    finally:
        session.close()


@router.post("/agents/{agent_id}/buffers", status_code=201)
def api_create_buffer(agent_id: str, data: BufferCreate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        b = Buffer(
            title=data.title,
            content=data.content,
            summary=data.summary,
        )
        session.add(b)
        session.commit()
        return {"id": b.id, "title": b.title}
    finally:
        session.close()


@router.put("/agents/{agent_id}/buffers/{bid}")
def api_update_buffer(agent_id: str, bid: int, data: BufferUpdate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        b = session.query(Buffer).get(bid)
        if not b:
            raise HTTPException(status_code=404, detail="Buffer not found")
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(b, field, value)
        session.commit()
        return {"id": b.id, "title": b.title}
    finally:
        session.close()


@router.delete("/agents/{agent_id}/buffers/{bid}")
def api_delete_buffer(agent_id: str, bid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        b = session.query(Buffer).get(bid)
        if not b:
            raise HTTPException(status_code=404, detail="Buffer not found")
        session.delete(b)
        session.commit()
        return {"deleted": bid}
    finally:
        session.close()


# ── System Prompts ──────────────────────────────────────────────────


@router.get("/agents/{agent_id}/system_prompts")
def api_list_system_prompts(agent_id: str):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = (
            session.query(SystemPrompt)
            .order_by(SystemPrompt.version.desc())
            .all()
        )
        return [{
            "id": sp.id, "version": sp.version, "is_active": sp.is_active,
            "content": sp.content,
            "created_at": str(sp.created_at), "updated_at": str(sp.updated_at),
        } for sp in rows]
    finally:
        session.close()


@router.get("/agents/{agent_id}/system_prompts/{spid}")
def api_get_system_prompt(agent_id: str, spid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        sp = session.query(SystemPrompt).get(spid)
        if not sp:
            raise HTTPException(status_code=404, detail="System prompt not found")
        return {
            "id": sp.id, "version": sp.version, "is_active": sp.is_active,
            "content": sp.content,
            "created_at": str(sp.created_at), "updated_at": str(sp.updated_at),
        }
    finally:
        session.close()


@router.post("/agents/{agent_id}/system_prompts", status_code=201)
def api_create_system_prompt(agent_id: str, data: SystemPromptCreate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        max_ver = session.query(func.max(SystemPrompt.version)).scalar() or 0
        session.query(SystemPrompt).update({SystemPrompt.is_active: False})
        sp = SystemPrompt(
            content=data.content,
            version=max_ver + 1,
            is_active=True,
        )
        session.add(sp)
        session.commit()
        return {"id": sp.id, "version": sp.version}
    finally:
        session.close()


@router.put("/agents/{agent_id}/system_prompts/{spid}")
def api_update_system_prompt(agent_id: str, spid: int, data: SystemPromptUpdate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        sp = session.query(SystemPrompt).get(spid)
        if not sp:
            raise HTTPException(status_code=404, detail="System prompt not found")
        if data.content is not None:
            sp.content = data.content
        if data.is_active is not None:
            if data.is_active:
                session.query(SystemPrompt).update({SystemPrompt.is_active: False})
            sp.is_active = data.is_active
        session.commit()
        return {"id": sp.id, "version": sp.version}
    finally:
        session.close()


@router.delete("/agents/{agent_id}/system_prompts/{spid}")
def api_delete_system_prompt(agent_id: str, spid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        sp = session.query(SystemPrompt).get(spid)
        if not sp:
            raise HTTPException(status_code=404, detail="System prompt not found")
        session.delete(sp)
        session.commit()
        return {"deleted": spid}
    finally:
        session.close()


# ── Tool Calls ──────────────────────────────────────────────────────


@router.get("/agents/{agent_id}/tool_calls")
def api_list_tool_calls(
    agent_id: str,
    tool_name: str | None = None,
    limit: int = Query(default=50, le=200),
):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        q = session.query(ToolCall)
        if tool_name:
            q = q.filter(ToolCall.tool_name == tool_name)
        rows = q.order_by(ToolCall.created_at.desc()).limit(limit).all()
        return [{
            "id": tc.id, "tool_name": tc.tool_name, "status": tc.status,
            "input_summary": tc.input_summary, "output_summary": tc.output_summary,
            "duration_ms": tc.duration_ms, "source": tc.source,
            "created_at": str(tc.created_at),
        } for tc in rows]
    finally:
        session.close()


@router.get("/agents/{agent_id}/tool_calls/stats")
def api_tool_call_stats(agent_id: str):
    db_path = get_agent_db_path(agent_id)
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
        return [{
            "tool_name": r.tool_name,
            "total_calls": r.total_calls,
            "success_count": r.success_count or 0,
            "error_count": r.error_count or 0,
            "avg_duration_ms": round(r.avg_duration_ms, 1) if r.avg_duration_ms else 0,
        } for r in rows]
    finally:
        session.close()


# ── Awakenings ──────────────────────────────────────────────────────


@router.get("/agents/{agent_id}/awakenings")
def api_list_awakenings(agent_id: str):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = (
            session.query(Awakening)
            .order_by(Awakening.created_at.desc())
            .limit(50)
            .all()
        )
        return [{
            "id": aw.id,
            "loaded_system_prompt_version": aw.loaded_system_prompt_version,
            "total_tokens": aw.total_tokens,
            "created_at": str(aw.created_at),
        } for aw in rows]
    finally:
        session.close()


@router.get("/agents/{agent_id}/awakenings/{aid}")
def api_get_awakening(agent_id: str, aid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        aw = session.query(Awakening).get(aid)
        if not aw:
            raise HTTPException(status_code=404, detail="Awakening not found")
        return {
            "id": aw.id,
            "loaded_system_prompt_version": aw.loaded_system_prompt_version,
            "loaded_todos": json.loads(aw.loaded_todos) if aw.loaded_todos else [],
            "loaded_skills": json.loads(aw.loaded_skills) if aw.loaded_skills else [],
            "loaded_memories": json.loads(aw.loaded_memories) if aw.loaded_memories else [],
            "loaded_buffers": json.loads(aw.loaded_buffers) if aw.loaded_buffers else [],
            "loaded_tool_calls": json.loads(aw.loaded_tool_calls) if aw.loaded_tool_calls else [],
            "total_tokens": aw.total_tokens,
            "created_at": str(aw.created_at),
        }
    finally:
        session.close()


# ── MCP Servers ─────────────────────────────────────────────────────


@router.get("/agents/{agent_id}/mcp_servers")
def api_list_mcp_servers(agent_id: str):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = session.query(McpServer).order_by(McpServer.name).all()
        return [{
            "id": s.id, "name": s.name, "server_type": s.server_type,
            "command": s.command,
            "args": json.loads(s.args) if s.args else None,
            "env": json.loads(s.env) if s.env else None,
            "is_enabled": s.is_enabled,
            "created_at": str(s.created_at), "updated_at": str(s.updated_at),
        } for s in rows]
    finally:
        session.close()


@router.get("/agents/{agent_id}/mcp_servers/{sid}")
def api_get_mcp_server(agent_id: str, sid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        s = session.query(McpServer).get(sid)
        if not s:
            raise HTTPException(status_code=404, detail="MCP server not found")
        return {
            "id": s.id, "name": s.name, "server_type": s.server_type,
            "command": s.command,
            "args": json.loads(s.args) if s.args else None,
            "env": json.loads(s.env) if s.env else None,
            "is_enabled": s.is_enabled,
            "created_at": str(s.created_at), "updated_at": str(s.updated_at),
        }
    finally:
        session.close()


@router.post("/agents/{agent_id}/mcp_servers", status_code=201)
def api_create_mcp_server(agent_id: str, data: McpServerCreate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        s = McpServer(
            name=data.name,
            server_type=data.server_type,
            command=data.command,
            args=json.dumps(data.args) if data.args else None,
            env=json.dumps(data.env) if data.env else None,
            is_enabled=data.is_enabled,
        )
        session.add(s)
        session.commit()
        return {"id": s.id, "name": s.name}
    finally:
        session.close()


@router.put("/agents/{agent_id}/mcp_servers/{sid}")
def api_update_mcp_server(agent_id: str, sid: int, data: McpServerUpdate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        s = session.query(McpServer).get(sid)
        if not s:
            raise HTTPException(status_code=404, detail="MCP server not found")
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == "args":
                setattr(s, field, json.dumps(value) if value is not None else None)
            elif field == "env":
                setattr(s, field, json.dumps(value) if value is not None else None)
            else:
                setattr(s, field, value)
        session.commit()
        return {"id": s.id, "name": s.name}
    finally:
        session.close()


@router.delete("/agents/{agent_id}/mcp_servers/{sid}")
def api_delete_mcp_server(agent_id: str, sid: int):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        s = session.query(McpServer).get(sid)
        if not s:
            raise HTTPException(status_code=404, detail="MCP server not found")
        session.delete(s)
        session.commit()
        return {"deleted": sid}
    finally:
        session.close()


# ── Schedule Config ─────────────────────────────────────────────────


@router.get("/agents/{agent_id}/schedule")
def api_get_schedule(agent_id: str):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        config = session.query(AgentScheduleConfig).first()
        if not config:
            return {
                "is_enabled": False,
                "interval_seconds": 300,
                "max_turns": 20,
                "model": "claude-sonnet-4-5",
                "initial_prompt": "Start by calling awaken with include_tool_history=true, then act according to your system prompt.",
                "last_run_at": None,
                "last_run_status": None,
                "last_run_error": None,
                "total_runs": 0,
            }
        return {
            "is_enabled": config.is_enabled,
            "interval_seconds": config.interval_seconds,
            "max_turns": config.max_turns,
            "model": config.model,
            "initial_prompt": config.initial_prompt,
            "last_run_at": str(config.last_run_at) if config.last_run_at else None,
            "last_run_status": config.last_run_status,
            "last_run_error": config.last_run_error,
            "total_runs": config.total_runs,
        }
    finally:
        session.close()


@router.put("/agents/{agent_id}/schedule")
def api_update_schedule(agent_id: str, data: ScheduleConfigUpdate):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        config = session.query(AgentScheduleConfig).first()
        if not config:
            config = AgentScheduleConfig()
            session.add(config)
            session.flush()
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)
        session.commit()
        return {
            "is_enabled": config.is_enabled,
            "interval_seconds": config.interval_seconds,
            "max_turns": config.max_turns,
            "model": config.model,
            "initial_prompt": config.initial_prompt,
        }
    finally:
        session.close()


# ── Scheduled Runs ──────────────────────────────────────────────────


@router.get("/agents/{agent_id}/scheduled_runs")
def api_list_scheduled_runs(
    agent_id: str,
    limit: int = Query(default=20, le=100),
):
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        rows = (
            session.query(ScheduledRun)
            .order_by(ScheduledRun.created_at.desc())
            .limit(limit)
            .all()
        )
        return [{
            "id": r.id, "status": r.status, "model": r.model,
            "num_turns": r.num_turns, "duration_ms": r.duration_ms,
            "error_message": r.error_message,
            "response_summary": r.response_summary,
            "awakening_id": r.awakening_id,
            "created_at": str(r.created_at),
        } for r in rows]
    finally:
        session.close()
