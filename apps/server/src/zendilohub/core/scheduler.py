import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    name: str
    every_seconds: float
    run: Callable[[], Awaitable[object]]


class Scheduler:
    """Runs periodic jobs (clean-ups) in the web process; a failing run is logged and retried next time."""

    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self._tasks: list[asyncio.Task[None]] = []

    def every(self, seconds: float, name: str, run: Callable[[], Awaitable[object]]) -> None:
        self.jobs.append(Job(name, seconds, run))

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._loop(job), name=f'job:{job.name}') for job in self.jobs]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def run_all(self) -> None:
        """Every job once, now (tests, CLI)."""
        for job in self.jobs:
            await job.run()

    async def _loop(self, job: Job) -> None:
        while True:
            try:
                await job.run()
            except Exception:
                logger.exception('Scheduled job failed', extra={'job': job.name})
            await asyncio.sleep(job.every_seconds)
