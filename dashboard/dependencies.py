"""FastAPI dependencies for AgentDB Dashboard."""

import os
from pathlib import Path
from typing import Generator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import get_session

AGENTS_DIR = Path(os.environ.get("AGENTDB_AGENTS_DIR", "agents"))


def get_agents_dir() -> Path:
    return AGENTS_DIR


def list_agent_ids() -> list[str]:
    agents_dir = get_agents_dir()
    if not agents_dir.exists():
        return []
    return sorted(p.stem for p in agents_dir.glob("*.db"))


def get_agent_db_path(agent_id: str) -> Path:
    agents_dir = get_agents_dir()
    path = agents_dir / f"{agent_id}.db"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return path


def get_agent_session(agent_id: str) -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy session for an agent DB."""
    db_path = get_agent_db_path(agent_id)
    session = get_session(str(db_path))
    try:
        yield session
    finally:
        session.close()
        if hasattr(session, "_engine"):
            session._engine.dispose()
