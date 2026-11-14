from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import argon2
import httpx

from zendilohub.core.application import Application
from zendilohub.core.config import AppConfig, load_config
from zendilohub.core.module import AppModule, ModuleContext, ModuleFactory
from zendilohub.modules.channels.channels_module import create_channels_module
from zendilohub.modules.identity.identity_module import create_identity_module
from zendilohub.modules.identity.infrastructure.security import Argon2PasswordHasher
from zendilohub.modules.tickets.tickets_module import create_tickets_module
from zendilohub.providers import providers

from .fakes import FakeClock, FakeWebsites, MemoryJobs, MemoryMailer, SequenceIds
from .mail_server import FakeMailServer
from .services import Services
from .writer import FakeWriter

# Cheap Argon2 parameters; the real cost would make the suite slow.
FAST_HASHER = Argon2PasswordHasher(argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


def _fast_identity(context: ModuleContext) -> AppModule:
    return create_identity_module(context, hasher=FAST_HASHER)


def fast_providers(mail_server: FakeMailServer | None = None, writer: FakeWriter | None = None) -> list[ModuleFactory]:
    """The real modules, with test doubles where the real thing is slow (or a mail server, or Claude)."""
    server = mail_server or FakeMailServer()
    assistant = writer or FakeWriter()

    def tickets(context: ModuleContext) -> AppModule:
        return create_tickets_module(context, writer=assistant)

    def channels(context: ModuleContext) -> AppModule:
        return create_channels_module(context, mailbox=server, outbox=server)

    replacements: dict[ModuleFactory, ModuleFactory] = {
        create_identity_module: _fast_identity,
        create_channels_module: channels,
        create_tickets_module: tickets,
    }
    return [replacements.get(factory, factory) for factory in providers]


TEMPLATE_DATABASE = 'zendilohub_template'

BASE_URL = 'http://zendilohub.test'


def make_config(services: Services, data_dir: Path, database: str = 'zendilohub', **overrides: Any) -> AppConfig:
    # Most tests use the SaaS mode (open sign-up, many organizations); the self-hosted ones pass multi_tenant=False.
    config = load_config({'ZENDILOHUB_DATA_DIR': str(data_dir), 'ZENDILOHUB_MULTI_TENANT': '1'})
    return replace(
        config,
        database_url=services.database(database),
        redis_url=services.redis_url,
        **overrides,
    )


async def create_template_database(services: Services, data_dir: Path) -> None:
    """Migrates a database once per session; every test app starts from a copy of it."""
    services.create_database(TEMPLATE_DATABASE)
    app = Application.create(make_config(services, data_dir, TEMPLATE_DATABASE), modules=providers, role='cli')
    await app.db.open()
    try:
        await app.migrate()
    finally:
        await app.shutdown()


@dataclass(frozen=True)
class AppUnderTest:
    app: Application
    client: httpx.AsyncClient
    clock: FakeClock
    ids: SequenceIds
    mailer: MemoryMailer
    jobs: MemoryJobs
    websites: FakeWebsites
    mail: FakeMailServer
    writer: FakeWriter

    async def run_jobs(self) -> None:
        """Runs the enqueued jobs (and the ones they enqueue), as a worker would."""
        while self.jobs.enqueued:
            task, args = self.jobs.enqueued.pop(0)
            await self.app.run_task(task, *args)

    async def run_delayed(self) -> list[float]:
        """Runs the jobs enqueued for later as if their time had come (and then the rest); returns their delays."""
        delayed, self.jobs.delayed = self.jobs.delayed, []
        for task, args, _delay in delayed:
            await self.app.run_task(task, *args)
        await self.run_jobs()
        return [delay for _task, _args, delay in delayed]

    @property
    def config(self) -> AppConfig:
        return self.app.config

    def new_client(self) -> httpx.AsyncClient:
        """Another browser: its own cookies (session)."""
        transport = httpx.ASGITransport(app=self.app.http.app, raise_app_exceptions=False)
        return httpx.AsyncClient(transport=transport, base_url=BASE_URL)


@asynccontextmanager
async def running_app(
    services: Services,
    data_dir: Path,
    name: str,
    *,
    modules: Sequence[ModuleFactory] | None = None,
    **overrides: Any,
) -> AsyncIterator[AppUnderTest]:
    """A booted app on a fresh copy of the migrated database, with an HTTP client for it."""
    services.create_database(name, template=TEMPLATE_DATABASE)
    clock = FakeClock()
    ids = SequenceIds()
    mailer = MemoryMailer()
    jobs = MemoryJobs()
    websites = FakeWebsites()
    mail = FakeMailServer()
    writer = FakeWriter()
    app = Application.create(
        make_config(services, data_dir, name, **overrides),
        modules=fast_providers(mail, writer) if modules is None else modules,
        clock=clock,
        ids=ids,
        mailer=mailer,
        jobs=jobs,
        fetcher=websites,
    )
    # Rate limits and queues must not leak from one test into the next.
    await app.context.redis.flushdb()
    await app.start(schedule=False)
    transport = httpx.ASGITransport(app=app.http.app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            yield AppUnderTest(app, client, clock, ids, mailer, jobs, websites, mail, writer)
    finally:
        await app.shutdown()
        services.drop_database(name)
