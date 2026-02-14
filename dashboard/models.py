"""SQLAlchemy models for AgentDB Dashboard.

These models map to the same schema used by the MCP Server.
The dashboard uses read-only connections to query agent databases.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    priority = Column(Integer, nullable=False, default=5)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    category = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    full_doc = Column(Text)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    importance = Column(Float, nullable=False, default=0.5)
    mem_type = Column(String, nullable=False, default="fact")
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class Buffer(Base):
    __tablename__ = "buffers"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text)
    created_at = Column(DateTime)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True)
    tool_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="success")
    input_summary = Column(Text)
    output_summary = Column(Text)
    duration_ms = Column(Integer)
    source = Column(String, nullable=False, default="auto")
    created_at = Column(DateTime)


class Awakening(Base):
    __tablename__ = "awakenings"

    id = Column(Integer, primary_key=True)
    loaded_system_prompt_version = Column(Integer)
    loaded_todos = Column(Text)  # JSON array
    loaded_skills = Column(Text)  # JSON array
    loaded_memories = Column(Text)  # JSON array
    loaded_buffers = Column(Text)  # JSON array
    loaded_tool_calls = Column(Text)  # JSON array
    total_tokens = Column(Integer)
    created_at = Column(DateTime)


class McpServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    server_type = Column(String, nullable=False, default="stdio")
    command = Column(String, nullable=False)
    args = Column(Text)  # JSON array
    env = Column(Text)   # JSON object
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class AgentScheduleConfig(Base):
    __tablename__ = "agent_schedule_config"

    id = Column(Integer, primary_key=True)
    is_enabled = Column(Boolean, nullable=False, default=False)
    interval_seconds = Column(Integer, nullable=False, default=300)
    max_turns = Column(Integer, nullable=False, default=20)
    model = Column(String, nullable=False, default="claude-sonnet-4-5")
    initial_prompt = Column(Text, nullable=False, default="Start by calling awaken with include_tool_history=true, then act according to your system prompt.")
    last_run_at = Column(DateTime)
    last_run_status = Column(String)
    last_run_error = Column(Text)
    total_runs = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class ScheduledRun(Base):
    __tablename__ = "scheduled_runs"

    id = Column(Integer, primary_key=True)
    status = Column(String, nullable=False, default="running")
    model = Column(String)
    num_turns = Column(Integer)
    duration_ms = Column(Integer)
    error_message = Column(Text)
    response_summary = Column(Text)
    awakening_id = Column(Integer)
    created_at = Column(DateTime)


def get_session(db_path: str) -> Session:
    """Create a session for an agent database.

    The returned session has a `_engine` attribute for cleanup.
    Caller should call session.close() when done. For full cleanup
    (releasing file handles), also call session._engine.dispose().
    """
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine)
    session = factory()
    session._engine = engine
    return session
