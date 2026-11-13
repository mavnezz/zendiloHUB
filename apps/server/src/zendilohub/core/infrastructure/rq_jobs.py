import asyncio
from datetime import timedelta
from functools import cached_property

from redis import Redis
from rq import Queue, Retry

RETRY = Retry(max=3, interval=[30, 120, 600])
"""A failing job (a provider down) is tried again later, three times."""


class RqJobQueue:
    """Puts jobs into Redis for `zendilohub worker` (RQ); every job runs the module task in a fresh process."""

    def __init__(self, redis_url: str, queue: str = 'default') -> None:
        self._redis_url = redis_url
        self._name = queue

    @cached_property
    def _queue(self) -> Queue:
        return Queue(self._name, connection=Redis.from_url(self._redis_url))

    async def enqueue(self, task: str, *args: str, delay: float = 0) -> None:
        # RQ speaks synchronous Redis; a short call, off the event loop.
        if delay > 0:
            # Delayed jobs wait in RQ's scheduled registry; the worker's scheduler moves them on when due.
            await asyncio.to_thread(
                self._queue.enqueue_in,
                timedelta(seconds=delay),
                'zendilohub.worker.run_task',
                task,
                *args,
                retry=RETRY,
                job_timeout=300,
            )
            return
        await asyncio.to_thread(
            self._queue.enqueue, 'zendilohub.worker.run_task', task, *args, retry=RETRY, job_timeout=300
        )
