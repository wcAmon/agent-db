"""HTML page routes for AgentDB Dashboard (FastAPI)."""

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func

from .dependencies import list_agent_ids, get_agents_dir, get_agent_db_path
from .models import (
    get_session,
    Awakening,
    Buffer,
    McpServer,
    AgentScheduleConfig,
    Memory,
    ScheduledRun,
    Skill,
    SystemPrompt,
    Todo,
    ToolCall,
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page: list all agents with summary stats."""
    agents = []
    for agent_id in list_agent_ids():
        agents_dir = get_agents_dir()
        db_path = agents_dir / f"{agent_id}.db"
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
            # Schedule config
            schedule = session.query(AgentScheduleConfig).first()
            agents.append({
                "id": agent_id,
                "last_awakening": last.created_at if last else None,
                "pending_todos": pending_count,
                "memory_count": memory_count,
                "schedule_enabled": schedule.is_enabled if schedule else False,
            })
        finally:
            session.close()
    templates = request.app.state.templates
    return templates.TemplateResponse("index.html", {"request": request, "agents": agents})


@router.get("/agent/{agent_id}", response_class=HTMLResponse)
async def agent_detail(request: Request, agent_id: str):
    """Agent detail page."""
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        prompt = (
            session.query(SystemPrompt)
            .filter(SystemPrompt.is_active == True)  # noqa: E712
            .order_by(SystemPrompt.version.desc())
            .first()
        )
        todos = (
            session.query(Todo)
            .filter(Todo.status == "pending")
            .order_by(Todo.priority.desc())
            .all()
        )
        memories = (
            session.query(Memory)
            .order_by(Memory.importance.desc())
            .limit(20)
            .all()
        )
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
        buffers = (
            session.query(Buffer)
            .order_by(Buffer.created_at.desc())
            .all()
        )
        tool_calls = (
            session.query(ToolCall)
            .order_by(ToolCall.created_at.desc())
            .limit(20)
            .all()
        )
        awakenings = (
            session.query(Awakening)
            .order_by(Awakening.created_at.desc())
            .limit(20)
            .all()
        )
        # MCP Servers
        mcp_servers = (
            session.query(McpServer)
            .order_by(McpServer.name)
            .all()
        )
        # Scheduled Runs
        scheduled_runs = (
            session.query(ScheduledRun)
            .order_by(ScheduledRun.created_at.desc())
            .limit(20)
            .all()
        )
        # Schedule Config
        schedule_config = session.query(AgentScheduleConfig).first()

        templates = request.app.state.templates
        return templates.TemplateResponse(
            "agent_detail.html",
            {
                "request": request,
                "agent_id": agent_id,
                "prompt": prompt,
                "todos": todos,
                "memories": memories,
                "skill_categories": skill_categories,
                "buffers": buffers,
                "tool_calls": tool_calls,
                "awakenings": awakenings,
                "mcp_servers": mcp_servers,
                "scheduled_runs": scheduled_runs,
                "schedule_config": schedule_config,
            },
        )
    finally:
        session.close()


@router.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    """Admin overview."""
    agents = []
    recent_tool_activity = []
    for agent_id in list_agent_ids():
        agents_dir = get_agents_dir()
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
            schedule = session.query(AgentScheduleConfig).first()
            agents.append({
                "id": agent_id,
                "pending_todos": pending_count,
                "memory_count": memory_count,
                "tool_call_count": tool_call_count,
                "last_awakening": last.created_at if last else None,
                "schedule_enabled": schedule.is_enabled if schedule else False,
                "schedule_interval": schedule.interval_seconds if schedule else None,
                "last_run_status": schedule.last_run_status if schedule else None,
                "last_run_at": schedule.last_run_at if schedule else None,
            })

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

    recent_tool_activity.sort(key=lambda x: str(x["created_at"] or ""), reverse=True)
    recent_tool_activity = recent_tool_activity[:30]

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "agents": agents, "recent_tool_activity": recent_tool_activity},
    )


@router.get("/agent/{agent_id}/awakening/{awakening_id}", response_class=HTMLResponse)
async def awakening_detail(request: Request, agent_id: str, awakening_id: int):
    """Awakening detail page."""
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        aw = session.query(Awakening).get(awakening_id)
        if not aw:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Awakening not found")

        todo_ids = json.loads(aw.loaded_todos) if aw.loaded_todos else []
        skill_ids = json.loads(aw.loaded_skills) if aw.loaded_skills else []
        memory_ids = json.loads(aw.loaded_memories) if aw.loaded_memories else []
        buffer_ids = json.loads(aw.loaded_buffers) if aw.loaded_buffers else []

        todos = session.query(Todo).filter(Todo.id.in_(todo_ids)).all() if todo_ids else []
        skills = session.query(Skill).filter(Skill.id.in_(skill_ids)).all() if skill_ids else []
        memories = session.query(Memory).filter(Memory.id.in_(memory_ids)).all() if memory_ids else []
        buffers = session.query(Buffer).filter(Buffer.id.in_(buffer_ids)).all() if buffer_ids else []

        prompt = None
        if aw.loaded_system_prompt_version:
            prompt = (
                session.query(SystemPrompt)
                .filter(SystemPrompt.version == aw.loaded_system_prompt_version)
                .first()
            )

        templates = request.app.state.templates
        return templates.TemplateResponse(
            "awakening_detail.html",
            {
                "request": request,
                "agent_id": agent_id,
                "awakening": aw,
                "prompt": prompt,
                "todos": todos,
                "skills": skills,
                "memories": memories,
                "buffers": buffers,
            },
        )
    finally:
        session.close()
