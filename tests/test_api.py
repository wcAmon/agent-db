"""Dashboard API endpoint tests.

Uses Flask test client to verify all REST API routes.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from agentdb_server.db import DatabaseManager


@pytest.fixture
def tmp_agents_dir():
    d = tempfile.mkdtemp(prefix="agentdb_api_test_")
    yield d
    # Windows: SQLAlchemy may hold file handles; retry cleanup
    import gc
    gc.collect()
    try:
        shutil.rmtree(d)
    except PermissionError:
        pass  # Windows file handle cleanup delay


@pytest.fixture
def seed_db(tmp_agents_dir):
    """Create a test agent database with seed data."""
    mgr = DatabaseManager(tmp_agents_dir)
    conn = mgr.get_write_connection("test_agent")

    # System prompt
    conn.execute(
        "INSERT INTO system_prompts (content, version, is_active) VALUES (?, 1, 1)",
        ("You are helpful.",),
    )
    # Todos
    conn.execute("INSERT INTO todos (content, priority) VALUES ('Task A', 8)")
    conn.execute("INSERT INTO todos (content, priority, status) VALUES ('Task B', 3, 'done')")
    # Memories
    conn.execute(
        "INSERT INTO memories (title, content, importance, mem_type) VALUES (?, ?, ?, ?)",
        ("Note 1", "Content 1", 0.9, "fact"),
    )
    # Skills
    conn.execute(
        "INSERT INTO skills (category, name, description) VALUES (?, ?, ?)",
        ("coding", "python", "Python programming"),
    )
    # Buffers
    conn.execute(
        "INSERT INTO buffers (title, content) VALUES (?, ?)",
        ("Doc 1", "Long document content"),
    )
    # Tool calls
    conn.execute(
        "INSERT INTO tool_calls (tool_name, status, duration_ms, source) VALUES (?, ?, ?, ?)",
        ("remember", "success", 15, "auto"),
    )
    conn.execute(
        "INSERT INTO tool_calls (tool_name, status, duration_ms, source) VALUES (?, ?, ?, ?)",
        ("add_todo", "error", 5, "manual"),
    )
    # Awakening
    conn.execute(
        "INSERT INTO awakenings (loaded_system_prompt_version, loaded_todos, "
        "loaded_skills, loaded_memories, loaded_buffers, total_tokens) "
        "VALUES (1, '[1]', '[1]', '[1]', '[1]', 500)"
    )
    conn.commit()
    mgr.close_all()
    return tmp_agents_dir


@pytest.fixture
def client(seed_db):
    os.environ["AGENTDB_AGENTS_DIR"] = seed_db
    # Must import after setting env var to pick up correct path
    from dashboard.app import app
    from dashboard import api as api_module

    app.config["TESTING"] = True
    # Update AGENTS_DIR in both app and api modules
    import dashboard.app as app_module
    app_module.AGENTS_DIR = Path(seed_db)
    api_module.AGENTS_DIR = Path(seed_db)

    with app.test_client() as c:
        yield c


class TestListAgents:
    def test_returns_agents(self, client):
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["id"] == "test_agent"
        assert data[0]["pending_todos"] == 1
        assert data[0]["memory_count"] == 1
        assert data[0]["tool_call_count"] == 2


class TestMemoriesAPI:
    def test_list(self, client):
        resp = client.get("/api/agents/test_agent/memories")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["title"] == "Note 1"

    def test_get(self, client):
        resp = client.get("/api/agents/test_agent/memories/1")
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "Note 1"

    def test_create(self, client):
        resp = client.post(
            "/api/agents/test_agent/memories",
            json={"title": "New", "content": "New content", "importance": 0.7},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["title"] == "New"

    def test_update(self, client):
        resp = client.put(
            "/api/agents/test_agent/memories/1",
            json={"title": "Updated"},
        )
        assert resp.status_code == 200
        # Verify
        resp2 = client.get("/api/agents/test_agent/memories/1")
        assert resp2.get_json()["title"] == "Updated"

    def test_delete(self, client):
        resp = client.delete("/api/agents/test_agent/memories/1")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] == 1
        resp2 = client.get("/api/agents/test_agent/memories/1")
        assert resp2.status_code == 404

    def test_create_missing_fields(self, client):
        resp = client.post(
            "/api/agents/test_agent/memories",
            json={"title": "No content"},
        )
        assert resp.status_code == 400

    def test_not_found_agent(self, client):
        resp = client.get("/api/agents/nonexistent/memories")
        assert resp.status_code == 404


class TestTodosAPI:
    def test_list(self, client):
        resp = client.get("/api/agents/test_agent/todos")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2

    def test_list_filter_status(self, client):
        resp = client.get("/api/agents/test_agent/todos?status=pending")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["content"] == "Task A"

    def test_create(self, client):
        resp = client.post(
            "/api/agents/test_agent/todos",
            json={"content": "New task", "priority": 9},
        )
        assert resp.status_code == 201

    def test_update(self, client):
        resp = client.put(
            "/api/agents/test_agent/todos/1",
            json={"status": "done"},
        )
        assert resp.status_code == 200

    def test_delete(self, client):
        resp = client.delete("/api/agents/test_agent/todos/1")
        assert resp.status_code == 200


class TestSkillsAPI:
    def test_list(self, client):
        resp = client.get("/api/agents/test_agent/skills")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_create(self, client):
        resp = client.post(
            "/api/agents/test_agent/skills",
            json={"category": "data", "name": "pandas", "description": "Data analysis"},
        )
        assert resp.status_code == 201

    def test_get_detail(self, client):
        resp = client.get("/api/agents/test_agent/skills/1")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "python"

    def test_update(self, client):
        resp = client.put(
            "/api/agents/test_agent/skills/1",
            json={"description": "Updated desc"},
        )
        assert resp.status_code == 200

    def test_delete(self, client):
        resp = client.delete("/api/agents/test_agent/skills/1")
        assert resp.status_code == 200


class TestBuffersAPI:
    def test_list(self, client):
        resp = client.get("/api/agents/test_agent/buffers")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_create(self, client):
        resp = client.post(
            "/api/agents/test_agent/buffers",
            json={"title": "New buf", "content": "data"},
        )
        assert resp.status_code == 201

    def test_get_detail(self, client):
        resp = client.get("/api/agents/test_agent/buffers/1")
        assert resp.status_code == 200
        assert resp.get_json()["content"] == "Long document content"

    def test_update(self, client):
        resp = client.put(
            "/api/agents/test_agent/buffers/1",
            json={"title": "Updated buf"},
        )
        assert resp.status_code == 200

    def test_delete(self, client):
        resp = client.delete("/api/agents/test_agent/buffers/1")
        assert resp.status_code == 200


class TestSystemPromptsAPI:
    def test_list(self, client):
        resp = client.get("/api/agents/test_agent/system_prompts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["is_active"] is True

    def test_create_new_version(self, client):
        resp = client.post(
            "/api/agents/test_agent/system_prompts",
            json={"content": "New prompt v2"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["version"] == 2

        # Old one should be deactivated
        resp2 = client.get("/api/agents/test_agent/system_prompts")
        prompts = resp2.get_json()
        active = [p for p in prompts if p["is_active"]]
        assert len(active) == 1
        assert active[0]["version"] == 2

    def test_delete(self, client):
        resp = client.delete("/api/agents/test_agent/system_prompts/1")
        assert resp.status_code == 200


class TestToolCallsAPI:
    def test_list(self, client):
        resp = client.get("/api/agents/test_agent/tool_calls")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2

    def test_list_filter(self, client):
        resp = client.get("/api/agents/test_agent/tool_calls?tool_name=remember")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["tool_name"] == "remember"

    def test_stats(self, client):
        resp = client.get("/api/agents/test_agent/tool_calls/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        # Should be ordered by total_calls desc (both have 1, so alphabetical)
        tool_names = {r["tool_name"] for r in data}
        assert "remember" in tool_names
        assert "add_todo" in tool_names


class TestAwakeningsAPI:
    def test_list(self, client):
        resp = client.get("/api/agents/test_agent/awakenings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1

    def test_get_detail(self, client):
        resp = client.get("/api/agents/test_agent/awakenings/1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_tokens"] == 500
        assert data["loaded_todos"] == [1]


class TestAdminPage:
    def test_admin_renders(self, client):
        resp = client.get("/admin")
        assert resp.status_code == 200
        assert b"Admin Overview" in resp.data
        assert b"test_agent" in resp.data

    def test_agent_detail_shows_tool_calls(self, client):
        resp = client.get("/agent/test_agent")
        assert resp.status_code == 200
        assert b"Tool Calls" in resp.data
        assert b"remember" in resp.data
