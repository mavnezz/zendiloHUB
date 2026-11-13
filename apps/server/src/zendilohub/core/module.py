from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from fastapi import APIRouter
from redis.asyncio import Redis

from .config import AppConfig
from .contracts import Contracts
from .database.database import Database
from .database.migration import Migration
from .domain.clock import Clock
from .domain.http_fetch import PublicFetcher
from .domain.id_generator import IdGenerator
from .domain.jobs import JobQueue
from .domain.mailer import Mailer
from .domain.rate_limiter import RateLimiter
from .events.event_bus import EventBus
from .http.http_kernel import HttpKernel
from .scheduler import Scheduler

type Role = Literal['web', 'worker', 'cli']
"""What the process does: serve the web app and API, process jobs, or run one command."""


@dataclass(frozen=True, kw_only=True)
class ModuleContext:
    """Shared infrastructure every module may use."""

    config: AppConfig
    role: Role
    db: Database
    redis: Redis
    http: HttpKernel
    events: EventBus
    clock: Clock
    ids: IdGenerator
    rate_limiter: RateLimiter
    mailer: Mailer
    jobs: JobQueue
    """Background work for the workers (the tasks of the modules)."""
    fetcher: PublicFetcher
    """Requests to addresses organizations configure (tools, webhooks): public internet only."""
    contracts: Contracts
    scheduler: Scheduler
    """Periodic jobs; they run in the web process only."""


class CliOutput(Protocol):
    def line(self, text: str) -> None: ...

    def error(self, text: str) -> None: ...


class CliCommand(Protocol):
    @property
    def usage(self) -> str: ...

    @property
    def description(self) -> str: ...

    async def run(self, args: Sequence[str], output: CliOutput) -> int:
        """Resolves to the process exit code."""
        ...


async def _nothing() -> None:
    pass


@dataclass(frozen=True, kw_only=True)
class AppModule:
    """The equivalent of a Laravel ServiceProvider: wires up one module."""

    name: str
    migrations: Sequence[Migration] = ()
    routers: Sequence[APIRouter] = ()
    root_routers: Sequence[APIRouter] = ()
    """Routes outside /api/v1 whose paths a protocol fixes, e.g. OAuth's /.well-known/… and MCP."""
    commands: Mapping[str, CliCommand] = field(default_factory=dict)
    tasks: Mapping[str, Callable[..., Awaitable[None]]] = field(default_factory=dict)
    """Background jobs a worker runs by name, e.g. `calls.summarize`."""
    boot: Callable[[], Awaitable[None]] = _nothing
    """Runs after all migrations, e.g. to start background work for the process's role."""
    shutdown: Callable[[], Awaitable[None]] = _nothing


type ModuleFactory = Callable[[ModuleContext], AppModule]
