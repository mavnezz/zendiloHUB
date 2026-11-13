from typing import Protocol


class JobQueue(Protocol):
    """Hands work to the background workers: a module's task by name (see `AppModule.tasks`) with text arguments."""

    async def enqueue(self, task: str, *args: str, delay: float = 0) -> None:
        """`delay`: run it that many seconds from now at the earliest (e.g. the next try of a webhook)."""
        ...
