"""Core integration tests for AgentDB.

Tests the database layer and tool functions directly (without MCP transport).
"""

import json
import os
import shutil
import tempfile

import pytest

from agentdb_server.db import DatabaseManager


@pytest.fixture
def tmp_agents_dir():
    d = tempfile.mkdtemp(prefix="agentdb_test_")
    yield d
    shutil.rmtree(d)


@pytest.fixture
def db(tmp_agents_dir):
    mgr = DatabaseManager(tmp_agents_dir)
    yield mgr
    mgr.close_all()


class TestDatabaseManager:
    def test_create_agent_on_connect(self, db, tmp_agents_dir):
        conn = db.get_write_connection("test_agent")
        assert conn is not None
        assert (db.agents_dir / "test_agent.db").exists()

    def test_list_agents(self, db):
        db.get_write_connection("alice")
        db.get_write_connection("bob")
        agents = db.list_agents()
        assert agents == ["alice", "bob"]

    def test_wal_mode(self, db):
        conn = db.get_write_connection("test")
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_read_connection(self, db):
        db.get_write_connection("reader_test")
        with db.read_connection("reader_test") as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {r[0] for r in tables}
            assert "system_prompts" in table_names
            assert "todos" in table_names
            assert "memories" in table_names

    def test_read_nonexistent_agent(self, db):
        with pytest.raises(FileNotFoundError):
            with db.read_connection("ghost"):
                pass

    def test_agent_id_sanitization(self, db):
        with pytest.raises(ValueError):
            db.get_write_connection("../../")

    def test_connection_reuse(self, db):
        conn1 = db.get_write_connection("reuse")
        conn2 = db.get_write_connection("reuse")
        assert conn1 is conn2


class TestSystemPrompt:
    def test_create_and_get(self, db):
        conn = db.get_write_connection("sp_test")
        conn.execute(
            "INSERT INTO system_prompts (content, version, is_active) VALUES (?, 1, 1)",
            ("You are a helpful assistant.",),
        )
        conn.commit()
        row = conn.execute(
            "SELECT content, version FROM system_prompts WHERE is_active = 1"
        ).fetchone()
        assert row["content"] == "You are a helpful assistant."
        assert row["version"] == 1

    def test_versioning(self, db):
        conn = db.get_write_connection("sp_ver")
        conn.execute(
            "INSERT INTO system_prompts (content, version, is_active) VALUES (?, 1, 1)",
            ("v1",),
        )
        conn.execute("UPDATE system_prompts SET is_active = 0")
        conn.execute(
            "INSERT INTO system_prompts (content, version, is_active) VALUES (?, 2, 1)",
            ("v2",),
        )
        conn.commit()
        row = conn.execute(
            "SELECT content, version FROM system_prompts WHERE is_active = 1"
        ).fetchone()
        assert row["content"] == "v2"
        assert row["version"] == 2


class TestTodos:
    def test_crud(self, db):
        conn = db.get_write_connection("todo_test")
        conn.execute(
            "INSERT INTO todos (content, priority) VALUES (?, ?)",
            ("Write tests", 8),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM todos WHERE id = 1").fetchone()
        assert row["content"] == "Write tests"
        assert row["priority"] == 8
        assert row["status"] == "pending"

    def test_priority_constraint(self, db):
        conn = db.get_write_connection("todo_constraint")
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO todos (content, priority) VALUES (?, ?)",
                ("Bad", 11),
            )

    def test_status_filter(self, db):
        conn = db.get_write_connection("todo_filter")
        conn.execute("INSERT INTO todos (content, priority) VALUES ('a', 5)")
        conn.execute("INSERT INTO todos (content, priority, status) VALUES ('b', 3, 'done')")
        conn.commit()
        pending = conn.execute(
            "SELECT * FROM todos WHERE status = 'pending'"
        ).fetchall()
        assert len(pending) == 1
        assert pending[0]["content"] == "a"


class TestMemories:
    def test_create_and_search(self, db):
        conn = db.get_write_connection("mem_test")
        conn.execute(
            "INSERT INTO memories (title, content, importance, mem_type) VALUES (?, ?, ?, ?)",
            ("Python tips", "Use list comprehensions", 0.8, "fact"),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM memories WHERE title LIKE ?", ("%Python%",)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["importance"] == 0.8

    def test_importance_ordering(self, db):
        conn = db.get_write_connection("mem_order")
        conn.execute(
            "INSERT INTO memories (title, content, importance) VALUES ('low', 'x', 0.1)"
        )
        conn.execute(
            "INSERT INTO memories (title, content, importance) VALUES ('high', 'x', 0.9)"
        )
        conn.commit()
        rows = conn.execute(
            "SELECT title FROM memories ORDER BY importance DESC"
        ).fetchall()
        assert rows[0]["title"] == "high"


class TestSkills:
    def test_catalog(self, db):
        conn = db.get_write_connection("skill_test")
        conn.execute(
            "INSERT INTO skills (category, name, description, full_doc) VALUES (?, ?, ?, ?)",
            ("coding", "python", "Python programming", "Full Python docs here"),
        )
        conn.execute(
            "INSERT INTO skills (category, name, description) VALUES (?, ?, ?)",
            ("coding", "javascript", "JS programming"),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT id, category, name, description FROM skills ORDER BY category, name"
        ).fetchall()
        assert len(rows) == 2
        assert rows[1]["name"] == "python"  # alphabetical


class TestBuffers:
    def test_store_and_load(self, db):
        conn = db.get_write_connection("buf_test")
        conn.execute(
            "INSERT INTO buffers (title, content) VALUES (?, ?)",
            ("Reference Doc", "A very long document..."),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM buffers WHERE id = 1").fetchone()
        assert row["title"] == "Reference Doc"
        assert row["content"] == "A very long document..."

    def test_list_no_content(self, db):
        conn = db.get_write_connection("buf_list")
        conn.execute(
            "INSERT INTO buffers (title, content) VALUES ('doc1', 'long content')"
        )
        conn.commit()
        rows = conn.execute("SELECT id, title FROM buffers").fetchall()
        assert len(rows) == 1
        assert rows[0]["title"] == "doc1"


class TestAwakenings:
    def test_record_awakening(self, db):
        conn = db.get_write_connection("aw_test")
        conn.execute(
            "INSERT INTO system_prompts (content, version, is_active) VALUES ('prompt', 1, 1)"
        )
        conn.execute("INSERT INTO todos (content, priority) VALUES ('task', 5)")
        conn.execute(
            "INSERT INTO memories (title, content, importance) VALUES ('mem', 'data', 0.7)"
        )
        conn.commit()

        conn.execute(
            "INSERT INTO awakenings (loaded_system_prompt_version, loaded_todos, "
            "loaded_skills, loaded_memories, loaded_buffers, total_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1, json.dumps([1]), json.dumps([]), json.dumps([1]), json.dumps([]), 500),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM awakenings WHERE id = 1").fetchone()
        assert row["total_tokens"] == 500
        assert json.loads(row["loaded_todos"]) == [1]


class TestToolCalls:
    def test_insert_and_query(self, db):
        conn = db.get_write_connection("tc_test")
        conn.execute(
            "INSERT INTO tool_calls (tool_name, status, input_summary, "
            "output_summary, duration_ms, source) VALUES (?, ?, ?, ?, ?, ?)",
            ("remember", "success", '{"title":"x"}', '{"id":1}', 42, "auto"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tool_calls WHERE id = 1").fetchone()
        assert row["tool_name"] == "remember"
        assert row["status"] == "success"
        assert row["duration_ms"] == 42
        assert row["source"] == "auto"

    def test_status_constraint(self, db):
        conn = db.get_write_connection("tc_constraint")
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO tool_calls (tool_name, status) VALUES (?, ?)",
                ("bad_tool", "unknown"),
            )

    def test_source_constraint(self, db):
        conn = db.get_write_connection("tc_src_constraint")
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO tool_calls (tool_name, source) VALUES (?, ?)",
                ("bad_tool", "external"),
            )

    def test_ordering(self, db):
        conn = db.get_write_connection("tc_order")
        conn.execute(
            "INSERT INTO tool_calls (tool_name, status) VALUES ('first', 'success')"
        )
        conn.execute(
            "INSERT INTO tool_calls (tool_name, status) VALUES ('second', 'error')"
        )
        conn.commit()
        rows = conn.execute(
            "SELECT tool_name FROM tool_calls ORDER BY id DESC"
        ).fetchall()
        assert rows[0]["tool_name"] == "second"

    def test_stats_aggregation(self, db):
        conn = db.get_write_connection("tc_stats")
        conn.execute(
            "INSERT INTO tool_calls (tool_name, status, duration_ms) VALUES ('add_todo', 'success', 10)"
        )
        conn.execute(
            "INSERT INTO tool_calls (tool_name, status, duration_ms) VALUES ('add_todo', 'success', 20)"
        )
        conn.execute(
            "INSERT INTO tool_calls (tool_name, status, duration_ms) VALUES ('add_todo', 'error', 5)"
        )
        conn.execute(
            "INSERT INTO tool_calls (tool_name, status, duration_ms) VALUES ('remember', 'success', 30)"
        )
        conn.commit()
        rows = conn.execute(
            "SELECT tool_name, COUNT(*) as cnt, "
            "SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as ok, "
            "AVG(duration_ms) as avg_ms "
            "FROM tool_calls GROUP BY tool_name ORDER BY cnt DESC"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["tool_name"] == "add_todo"
        assert rows[0]["cnt"] == 3
        assert rows[0]["ok"] == 2


class TestAwakeningToolCallsColumn:
    def test_loaded_tool_calls_column(self, db):
        conn = db.get_write_connection("aw_tc_test")
        conn.execute(
            "INSERT INTO awakenings (loaded_system_prompt_version, loaded_todos, "
            "loaded_skills, loaded_memories, loaded_buffers, loaded_tool_calls, total_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, "[]", "[]", "[]", "[]", json.dumps([1, 2, 3]), 100),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM awakenings WHERE id = 1").fetchone()
        assert json.loads(row["loaded_tool_calls"]) == [1, 2, 3]


class TestConcurrency:
    def test_reader_during_write(self, db):
        """Read connection should not block write connection (WAL mode)."""
        conn_w = db.get_write_connection("concurrent")
        conn_w.execute("INSERT INTO todos (content, priority) VALUES ('a', 5)")
        conn_w.commit()

        with db.read_connection("concurrent") as conn_r:
            rows = conn_r.execute("SELECT * FROM todos").fetchall()
            assert len(rows) == 1

            conn_w.execute("INSERT INTO todos (content, priority) VALUES ('b', 3)")
            conn_w.commit()

        with db.read_connection("concurrent") as conn_r:
            rows = conn_r.execute("SELECT * FROM todos").fetchall()
            assert len(rows) == 2


# ── New table tests ────────────────────────────────────────────────


class TestMcpServers:
    def test_create_mcp_server(self, db):
        conn = db.get_write_connection("mcp_test")
        conn.execute(
            "INSERT INTO mcp_servers (name, server_type, command, args, env) "
            "VALUES (?, ?, ?, ?, ?)",
            ("agentdb", "stdio", "agentdb-server", json.dumps(["--verbose"]), json.dumps({"KEY": "val"})),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM mcp_servers WHERE id = 1").fetchone()
        assert row["name"] == "agentdb"
        assert row["server_type"] == "stdio"
        assert row["command"] == "agentdb-server"
        assert json.loads(row["args"]) == ["--verbose"]
        assert json.loads(row["env"]) == {"KEY": "val"}
        assert row["is_enabled"] == 1

    def test_unique_name(self, db):
        conn = db.get_write_connection("mcp_unique")
        conn.execute(
            "INSERT INTO mcp_servers (name, command) VALUES ('srv1', 'cmd1')"
        )
        conn.commit()
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO mcp_servers (name, command) VALUES ('srv1', 'cmd2')"
            )

    def test_server_type_constraint(self, db):
        conn = db.get_write_connection("mcp_type")
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO mcp_servers (name, server_type, command) VALUES ('x', 'grpc', 'cmd')"
            )

    def test_list_enabled(self, db):
        conn = db.get_write_connection("mcp_enabled")
        conn.execute("INSERT INTO mcp_servers (name, command) VALUES ('a', 'cmd1')")
        conn.execute("INSERT INTO mcp_servers (name, command, is_enabled) VALUES ('b', 'cmd2', 0)")
        conn.commit()
        rows = conn.execute("SELECT * FROM mcp_servers WHERE is_enabled = 1").fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "a"


class TestAgentScheduleConfig:
    def test_create_default(self, db):
        conn = db.get_write_connection("sched_test")
        conn.execute("INSERT INTO agent_schedule_config DEFAULT VALUES")
        conn.commit()
        row = conn.execute("SELECT * FROM agent_schedule_config WHERE id = 1").fetchone()
        assert row["is_enabled"] == 0
        assert row["interval_seconds"] == 300
        assert row["max_turns"] == 20
        assert row["model"] == "claude-sonnet-4-5"
        assert row["total_runs"] == 0

    def test_update_config(self, db):
        conn = db.get_write_connection("sched_update")
        conn.execute("INSERT INTO agent_schedule_config DEFAULT VALUES")
        conn.execute(
            "UPDATE agent_schedule_config SET is_enabled = 1, interval_seconds = 60 WHERE id = 1"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM agent_schedule_config WHERE id = 1").fetchone()
        assert row["is_enabled"] == 1
        assert row["interval_seconds"] == 60

    def test_last_run_status_constraint(self, db):
        conn = db.get_write_connection("sched_status")
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO agent_schedule_config (last_run_status) VALUES ('unknown')"
            )


class TestScheduledRuns:
    def test_create_run(self, db):
        conn = db.get_write_connection("run_test")
        conn.execute(
            "INSERT INTO scheduled_runs (status, model, num_turns, duration_ms) "
            "VALUES ('success', 'claude-sonnet-4-5', 5, 1200)"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM scheduled_runs WHERE id = 1").fetchone()
        assert row["status"] == "success"
        assert row["model"] == "claude-sonnet-4-5"
        assert row["num_turns"] == 5
        assert row["duration_ms"] == 1200

    def test_status_constraint(self, db):
        conn = db.get_write_connection("run_constraint")
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO scheduled_runs (status) VALUES ('unknown')"
            )

    def test_error_run(self, db):
        conn = db.get_write_connection("run_error")
        conn.execute(
            "INSERT INTO scheduled_runs (status, error_message) "
            "VALUES ('error', 'API timeout')"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM scheduled_runs WHERE id = 1").fetchone()
        assert row["status"] == "error"
        assert row["error_message"] == "API timeout"

    def test_ordering(self, db):
        conn = db.get_write_connection("run_order")
        conn.execute("INSERT INTO scheduled_runs (status) VALUES ('success')")
        conn.execute("INSERT INTO scheduled_runs (status) VALUES ('error')")
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM scheduled_runs ORDER BY created_at DESC"
        ).fetchall()
        assert len(rows) == 2
