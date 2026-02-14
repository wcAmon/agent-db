"""Scheduler manager — periodically scans agents and runs due ones."""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from .config import load_agent_config
from .runner import run_agent, record_run

logger = logging.getLogger(__name__)


class SchedulerManager:
    def __init__(self, agents_dir: str = "agents", poll_interval: int = 30):
        self.agents_dir = Path(agents_dir)
        self.poll_interval = poll_interval
        self._running_agents: set[str] = set()

    def _scan_agents(self) -> list[str]:
        """List all agent IDs by scanning .db files."""
        if not self.agents_dir.exists():
            return []
        return sorted(p.stem for p in self.agents_dir.glob("*.db"))

    def _is_due(self, last_run_at: str | None, interval_seconds: int) -> bool:
        """Check if enough time has passed since last run."""
        if last_run_at is None:
            return True
        try:
            last_run = datetime.fromisoformat(last_run_at)
            return datetime.now() - last_run >= timedelta(seconds=interval_seconds)
        except (ValueError, TypeError):
            return True

    async def _run_agent(self, agent_id: str):
        """Run a single agent and record the result."""
        if agent_id in self._running_agents:
            logger.debug(f"Agent {agent_id} already running, skipping")
            return

        self._running_agents.add(agent_id)
        try:
            config = load_agent_config(agent_id, self.agents_dir)
            if config is None:
                return

            logger.info(f"Starting scheduled run for agent: {agent_id}")
            result = await run_agent(config)
            record_run(config, result)
            logger.info(
                f"Agent {agent_id} run completed: status={result.status}, "
                f"duration={result.duration_ms}ms, turns={result.num_turns}"
            )
        except Exception as e:
            logger.error(f"Error running agent {agent_id}: {e}")
        finally:
            self._running_agents.discard(agent_id)

    async def run_forever(self):
        """Main scheduler loop — scans agents and runs due ones."""
        logger.info(
            f"Scheduler started: agents_dir={self.agents_dir}, "
            f"poll_interval={self.poll_interval}s"
        )
        while True:
            try:
                for agent_id in self._scan_agents():
                    config = load_agent_config(agent_id, self.agents_dir)
                    if config is None:
                        continue
                    if not config.is_enabled:
                        continue
                    if not self._is_due(config.last_run_at, config.interval_seconds):
                        continue
                    if agent_id in self._running_agents:
                        continue

                    asyncio.create_task(self._run_agent(agent_id))

            except Exception as e:
                logger.error(f"Scheduler scan error: {e}")

            await asyncio.sleep(self.poll_interval)
