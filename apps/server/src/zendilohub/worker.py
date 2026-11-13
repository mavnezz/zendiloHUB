"""
`zendilohub worker`: runs the background jobs from Redis (RQ): e-mails and, as they arrive, mail fetching and webhooks.
Every job runs in a fresh child process (RQ forks), so a failing job cannot take the worker down.
Scale with more containers: `docker compose up -d --scale worker=3`.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from redis import Redis
from rq import Worker

from .core.application import Application
from .core.config import AppConfig, load_config
from .providers import providers

# In order of priority: a worker takes the next job from the first queue that has one.
QUEUES = ['critical', 'default', 'heavy']

WORKER_TTL = 60
"""An idle worker waits WORKER_TTL - 15 seconds for a job, then beats; the health check allows 120 seconds."""

logger = logging.getLogger(__name__)


def run_task(name: str, *args: str) -> None:
    """The function every RQ job calls: runs a module's task in a short-lived app (no web, no migrations)."""
    asyncio.run(_run_task(load_config(os.environ), name, args))


async def _run_task(config: AppConfig, name: str, args: tuple[str, ...]) -> None:
    app = Application.create(config, modules=providers, role='worker')
    await app.start(migrate=False)
    try:
        await app.run_task(name, *args)
    finally:
        await app.shutdown()


class HeartbeatWorker(Worker):
    """Touches a file with every heartbeat; the container's health check looks at its age."""

    heartbeat_file = Path(os.environ.get('ZENDILOHUB_WORKER_HEARTBEAT', '/tmp/zendilohub-worker.heartbeat'))

    def heartbeat(self, *args: Any, **kwargs: Any) -> None:
        super().heartbeat(*args, **kwargs)
        self.heartbeat_file.touch()


def run_worker(config: AppConfig) -> int:
    connection = Redis.from_url(config.redis_url)
    worker = HeartbeatWorker(QUEUES, connection=connection, worker_ttl=WORKER_TTL)
    HeartbeatWorker.heartbeat_file.touch()
    logger.info('Worker started', extra={'queues': QUEUES})
    # Logging is configured already (JSON on stdout); RQ must not install its own handler. The scheduler moves
    # delayed jobs and retries (which wait in RQ's scheduled registry) back into the queue; one worker holds it.
    worker.work(with_scheduler=True, logging_level=config.log_level.upper(), log_format='%(message)s')
    return 0
