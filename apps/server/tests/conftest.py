import itertools
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from redis.asyncio import Redis

from support.app import AppUnderTest, create_template_database, running_app
from support.services import Services, start_services
from zendilohub.core.database.database import Database

_names = itertools.count(1)


@pytest.fixture(scope='session')
def services() -> Iterator[Services]:
    with start_services() as services:
        yield services


@pytest.fixture
async def empty_db(services: Services) -> AsyncIterator[Database]:
    """A fresh, empty database (no migrations)."""
    name = f'test_empty_{next(_names)}'
    db = Database(services.create_database(name), max_size=4)
    await db.open()
    yield db
    await db.close()
    services.drop_database(name)


@pytest.fixture
async def redis(services: Services) -> AsyncIterator[Redis]:
    client = Redis.from_url(services.redis_url)
    await client.flushdb()
    yield client
    await client.aclose()


@pytest.fixture(scope='session')
async def template_database(services: Services, tmp_path_factory: pytest.TempPathFactory) -> None:
    await create_template_database(services, tmp_path_factory.mktemp('template'))


@pytest.fixture
async def app(services: Services, template_database: None, tmp_path: Path) -> AsyncIterator[AppUnderTest]:
    """The real app (all modules) on a fresh database, with an HTTP client."""
    async with running_app(services, tmp_path / 'data', f'test_app_{next(_names)}') as running:
        yield running


@pytest.fixture
async def self_hosted(services: Services, template_database: None, tmp_path: Path) -> AsyncIterator[AppUnderTest]:
    """The real app as a self-hosted instance (one organization, setup wizard, invited sign-ups only)."""
    async with running_app(services, tmp_path / 'data', f'test_app_{next(_names)}', multi_tenant=False) as running:
        yield running
