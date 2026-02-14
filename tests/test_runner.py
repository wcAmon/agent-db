"""Tests for agent_runner config loading and runner logic."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from agentdb_server.db import DatabaseManager
from agent_runner.config import load_agent_config, AgentRunConfig, McpServerConfig
from agent_runner.runner import RunResult, record_run


@pytest.fixture
def tmp_agents_dir():
    d = tempfile.mkdtemp(prefix="agentdb_runner_test_")
    yield Path(d)
    shutil.rmtree(d)


@pytest.fixture
def seeded_agents_dir(tmp_agents_dir):
    """Create a test agent with full config."""
    mgr = DatabaseManager(str(tmp_agents_dir))
    conn = mgr.get_write_connection("runner_test")

    # System prompt
    conn.execute(
        "INSERT INTO system_prompts (content, version, is_active) VALUES (?, 1, 1)",
        ("You are a test agent.",),
    )
    # Schedule config
    conn.execute(
        "INSERT INTO agent_schedule_config (is_enabled, interval_seconds, max_turns, model) "
        "VALUES (1, 60, 10, 'claude-sonnet-4-5')"
    )
    # MCP servers
    conn.execute(
        "INSERT INTO mcp_servers (name, command, args, env) VALUES (?, ?, ?, ?)",
        ("agentdb", "agentdb-server", json.dumps(["--verbose"]), json.dumps({"KEY": "val"})),
    )
    conn.execute(
        "INSERT INTO mcp_servers (name, command, is_enabled) VALUES (?, ?, 0)",
        ("disabled-srv", "some-cmd"),
    )
    conn.commit()
    mgr.close_all()
    return tmp_agents_dir


class TestLoadAgentConfig:
    def test_load_full_config(self, seeded_agents_dir):
        config = load_agent_config("runner_test", seeded_agents_dir)
        assert config is not None
        assert config.agent_id == "runner_test"
        assert config.system_prompt == "You are a test agent."
        assert config.is_enabled is True
        assert config.interval_seconds == 60
        assert config.max_turns == 10
        assert config.model == "claude-sonnet-4-5"

    def test_mcp_servers_only_enabled(self, seeded_agents_dir):
        config = load_agent_config("runner_test", seeded_agents_dir)
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0].name == "agentdb"
        assert config.mcp_servers[0].command == "agentdb-server"
        assert config.mcp_servers[0].args == ["--verbose"]
        assert config.mcp_servers[0].env == {"KEY": "val"}

    def test_nonexistent_agent(self, tmp_agents_dir):
        config = load_agent_config("ghost", tmp_agents_dir)
        assert config is None

    def test_agent_without_schedule(self, tmp_agents_dir):
        mgr = DatabaseManager(str(tmp_agents_dir))
        conn = mgr.get_write_connection("no_sched")
        conn.execute(
            "INSERT INTO system_prompts (content, version, is_active) VALUES ('test', 1, 1)"
        )
        conn.commit()
        mgr.close_all()

        config = load_agent_config("no_sched", tmp_agents_dir)
        assert config is not None
        assert config.is_enabled is False
        assert config.interval_seconds == 300


class TestRecordRun:
    def test_record_success(self, seeded_agents_dir):
        config = load_agent_config("runner_test", seeded_agents_dir)
        result = RunResult(
            status="success",
            num_turns=5,
            duration_ms=1200,
            response_summary="Agent completed tasks.",
        )
        record_run(config, result)

        # Verify in DB
        import sqlite3
        conn = sqlite3.connect(str(config.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM scheduled_runs ORDER BY id DESC LIMIT 1").fetchone()
        assert row["status"] == "success"
        assert row["num_turns"] == 5
        assert row["duration_ms"] == 1200

        sched = conn.execute("SELECT * FROM agent_schedule_config LIMIT 1").fetchone()
        assert sched["last_run_status"] == "success"
        assert sched["total_runs"] == 1
        conn.close()

    def test_record_error(self, seeded_agents_dir):
        config = load_agent_config("runner_test", seeded_agents_dir)
        result = RunResult(
            status="error",
            duration_ms=500,
            error_message="API timeout",
        )
        record_run(config, result)

        import sqlite3
        conn = sqlite3.connect(str(config.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM scheduled_runs ORDER BY id DESC LIMIT 1").fetchone()
        assert row["status"] == "error"
        assert row["error_message"] == "API timeout"
        conn.close()


class TestMcpServerConfig:
    def test_build_mcp_dict(self):
        """Test building the mcp_servers dict for ClaudeCodeOptions."""
        servers = [
            McpServerConfig(name="agentdb", command="agentdb-server", args=["--verbose"]),
            McpServerConfig(name="fs", command="fs-server"),
        ]
        mcp_dict = {}
        for srv in servers:
            entry = {"command": srv.command}
            if srv.args:
                entry["args"] = srv.args
            if srv.env:
                entry["env"] = srv.env
            mcp_dict[srv.name] = entry

        assert mcp_dict == {
            "agentdb": {"command": "agentdb-server", "args": ["--verbose"]},
            "fs": {"command": "fs-server"},
        }
