"""Pydantic models for request/response validation."""

from pydantic import BaseModel, Field


# ── Memory ─────────────────────────────────────────────────────────

class MemoryCreate(BaseModel):
    title: str
    content: str
    importance: float = 0.5
    mem_type: str = "fact"


class MemoryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    importance: float | None = None
    mem_type: str | None = None


# ── Todo ───────────────────────────────────────────────────────────

class TodoCreate(BaseModel):
    content: str
    priority: int = Field(default=5, ge=1, le=10)
    status: str = "pending"


class TodoUpdate(BaseModel):
    content: str | None = None
    priority: int | None = Field(default=None, ge=1, le=10)
    status: str | None = None


# ── Skill ──────────────────────────────────────────────────────────

class SkillCreate(BaseModel):
    category: str
    name: str
    description: str
    full_doc: str = ""


class SkillUpdate(BaseModel):
    category: str | None = None
    name: str | None = None
    description: str | None = None
    full_doc: str | None = None


# ── Buffer ─────────────────────────────────────────────────────────

class BufferCreate(BaseModel):
    title: str
    content: str
    summary: str | None = None


class BufferUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None


# ── System Prompt ──────────────────────────────────────────────────

class SystemPromptCreate(BaseModel):
    content: str


class SystemPromptUpdate(BaseModel):
    content: str | None = None
    is_active: bool | None = None


# ── MCP Server ─────────────────────────────────────────────────────

class McpServerCreate(BaseModel):
    name: str
    server_type: str = "stdio"
    command: str
    args: list[str] | None = None
    env: dict[str, str] | None = None
    is_enabled: bool = True


class McpServerUpdate(BaseModel):
    name: str | None = None
    server_type: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    is_enabled: bool | None = None


# ── Schedule Config ────────────────────────────────────────────────

class ScheduleConfigUpdate(BaseModel):
    is_enabled: bool | None = None
    interval_seconds: int | None = None
    max_turns: int | None = None
    model: str | None = None
    initial_prompt: str | None = None
