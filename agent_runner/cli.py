"""CLI entry point for the scheduled agent runner."""

import argparse
import asyncio
import logging
import os

from .scheduler import SchedulerManager


def main():
    parser = argparse.ArgumentParser(description="AgentDB Scheduled Runner")
    parser.add_argument(
        "--agents-dir",
        default=os.environ.get("AGENTDB_AGENTS_DIR", "agents"),
        help="Path to agents database directory (default: ./agents)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="How often to scan for due agents, in seconds (default: 30)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    scheduler = SchedulerManager(
        agents_dir=args.agents_dir,
        poll_interval=args.poll_interval,
    )

    asyncio.run(scheduler.run_forever())


if __name__ == "__main__":
    main()
