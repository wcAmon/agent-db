"""Database connection management for AgentDB.

Each agent gets its own SQLite database file with WAL mode enabled.
Write connections are long-lived and reused; read connections are ephemeral.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


class DatabaseManager:
    def __init__(self, agents_dir: str = "agents"):
        self.agents_dir = Path(agents_dir)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self._write_connections: dict[str, sqlite3.Connection] = {}
        self._schema_sql = self._load_schema()

    def _load_schema(self) -> str:
        schema_path = Path(__file__).parent / "schema.sql"
        return schema_path.read_text(encoding="utf-8")

    def _db_path(self, agent_id: str) -> Path:
        # Sanitize agent_id to prevent path traversal
        safe_id = "".join(c for c in agent_id if c.isalnum() or c in "-_")
        if not safe_id:
            raise ValueError(f"Invalid agent_id: {agent_id}")
        return self.agents_dir / f"{safe_id}.db"

    def _init_db(self, conn: sqlite3.Connection):
        """Initialize database with schema and WAL mode."""
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.executescript(self._schema_sql)
        self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection):
        """Apply migrations for columns added after initial schema."""
        try:
            conn.execute("ALTER TABLE awakenings ADD COLUMN loaded_tool_calls TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

    def get_write_connection(self, agent_id: str) -> sqlite3.Connection:
        """Get or create a long-lived write connection for an agent.

        Creates the database file and schema if it doesn't exist.
        """
        if agent_id not in self._write_connections:
            db_path = self._db_path(agent_id)
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            self._init_db(conn)
            self._write_connections[agent_id] = conn
        return self._write_connections[agent_id]

    @contextmanager
    def read_connection(self, agent_id: str):
        """Create a short-lived read-only connection for an agent.

        Used by the Dashboard for concurrent reads without blocking writers.
        """
        db_path = self._db_path(agent_id)
        if not db_path.exists():
            raise FileNotFoundError(f"Agent '{agent_id}' not found")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def list_agents(self) -> list[str]:
        """List all agent IDs by scanning the agents directory."""
        return sorted(p.stem for p in self.agents_dir.glob("*.db"))

    def agent_exists(self, agent_id: str) -> bool:
        return self._db_path(agent_id).exists()

    def close_all(self):
        """Close all write connections. Call on shutdown."""
        for conn in self._write_connections.values():
            conn.close()
        self._write_connections.clear()
