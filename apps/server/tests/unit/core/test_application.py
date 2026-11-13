import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter

from support.app import make_config
from support.fakes import MemoryOutput
from support.services import Services
from zendilohub.core.application import Application
from zendilohub.core.database.migration import SqlMigration
from zendilohub.core.domain.app_domain_error import ConflictError
from zendilohub.core.http.access import Public
from zendilohub.core.module import AppModule, CliOutput, ModuleContext, ModuleFactory


class Shout:
    usage = 'shout <text>'
    description = 'Prints the text in capitals'

    async def run(self, args: Sequence[str], output: CliOutput) -> int:
        if not args:
            raise ConflictError('nothing_to_shout', 'Nothing to shout')
        output.line(' '.join(args).upper())
        return 0


def _module(name: str, journal: list[str]) -> ModuleFactory:
    def factory(context: ModuleContext) -> AppModule:
        router = APIRouter()

        @router.get(f'/{name}', dependencies=[Public])
        async def hello() -> dict[str, str]:
            return {'module': name, 'role': context.role}

        async def boot() -> None:
            journal.append(f'boot {name}')

        async def shutdown() -> None:
            journal.append(f'shutdown {name}')

        return AppModule(
            name=name,
            migrations=[
                SqlMigration(f'2026_10_22_00000{len(name)}_create_{name}_table', f'CREATE TABLE {name} (id INT)')
            ],
            routers=[router],
            commands={'shout': Shout()} if name == 'alpha' else {},
            boot=boot,
            shutdown=shutdown,
        )

    return factory


@pytest.fixture
async def database(services: Services) -> AsyncIterator[str]:
    services.create_database('test_application')
    yield 'test_application'
    services.drop_database('test_application')


async def test_boots_modules_in_order_and_shuts_them_down_in_reverse(
    services: Services, database: str, tmp_path: Path
) -> None:
    journal: list[str] = []
    app = Application.create(
        make_config(services, tmp_path, database), modules=[_module('alpha', journal), _module('beta', journal)]
    )
    await app.start()
    transport = httpx.ASGITransport(app=app.http.app)
    async with httpx.AsyncClient(transport=transport, base_url='http://zendilohub.test') as client:
        assert (await client.get('/api/v1/beta')).json() == {'module': 'beta', 'role': 'web'}
        assert (await client.get('/health')).json() == {
            'status': 'ok',
            'checks': {'database': 'ok', 'redis': 'ok'},
        }
    await app.shutdown()

    assert journal == ['boot alpha', 'boot beta', 'shutdown beta', 'shutdown alpha']


async def test_migrates_every_module(services: Services, database: str, tmp_path: Path) -> None:
    app = Application.create(
        make_config(services, tmp_path, database), modules=[_module('alpha', []), _module('beta', [])]
    )
    await app.start()
    try:
        assert await app.migrate() == []
        async with app.db.connection() as connection:
            rows = await (await connection.execute('SELECT migration FROM migrations ORDER BY id')).fetchall()
        assert [row['migration'] for row in rows] == [
            '2026_10_22_000004_create_beta_table',
            '2026_10_22_000005_create_alpha_table',
        ]
    finally:
        await app.shutdown()


async def test_runs_cli_commands(services: Services, database: str, tmp_path: Path) -> None:
    app = Application.create(make_config(services, tmp_path, database), modules=[_module('alpha', [])], role='cli')
    await app.start()
    try:
        output = MemoryOutput()
        assert await app.run_command(['shout', 'hello', 'world'], output) == 0
        assert output.lines == ['HELLO WORLD']

        output = MemoryOutput()
        assert await app.run_command(['shout'], output) == 1
        assert output.errors == ['Nothing to shout']

        output = MemoryOutput()
        assert await app.run_command(['whisper'], output) == 1
        assert output.errors[0] == 'Unknown command "whisper".'
        assert 'shout <text>' in output.errors[2]

        output = MemoryOutput()
        assert await app.run_command([], output) == 1
        assert output.errors[0] == 'No command given.'
    finally:
        await app.shutdown()


async def test_serves_the_web_app_in_the_web_role_only(
    services: Services, database: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    web_dir = tmp_path / 'web'
    web_dir.mkdir()
    (web_dir / 'index.html').write_text('<div id="app"></div>')
    config = replace(make_config(services, tmp_path, database), web_dir=web_dir)

    for role, served in (('web', True), ('worker', False)):
        app = Application.create(config, modules=[], role=role)  # type: ignore[arg-type]
        await app.start()
        transport = httpx.ASGITransport(app=app.http.app)
        async with httpx.AsyncClient(transport=transport, base_url='http://zendilohub.test') as client:
            assert ('<div id="app">' in (await client.get('/')).text) is served
        await app.shutdown()

    app = Application.create(replace(config, web_dir=tmp_path / 'missing'), modules=[])
    with caplog.at_level(logging.WARNING):
        await app.start()
    await app.shutdown()
    assert 'No web app build found, serving the API only' in caplog.text


async def test_reports_redis_as_down_when_it_is_unreachable(services: Services, database: str, tmp_path: Path) -> None:
    config = replace(make_config(services, tmp_path, database), redis_url='redis://127.0.0.1:1/0')
    app = Application.create(config, modules=[])
    await app.start()
    transport = httpx.ASGITransport(app=app.http.app)
    async with httpx.AsyncClient(transport=transport, base_url='http://zendilohub.test') as client:
        response = await client.get('/health')
    await app.shutdown()

    assert response.status_code == 503
    assert response.json()['checks'] == {'database': 'ok', 'redis': 'down'}


async def test_logs_requests_at_debug_level(
    services: Services, database: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    app = Application.create(make_config(services, tmp_path, database), modules=[_module('alpha', [])])
    await app.start()
    transport = httpx.ASGITransport(app=app.http.app)
    with caplog.at_level(logging.DEBUG, logger='zendilohub.http'):
        async with httpx.AsyncClient(transport=transport, base_url='http://zendilohub.test') as client:
            await client.get('/api/v1/alpha')
    await app.shutdown()

    record = next(record for record in caplog.records if record.getMessage() == 'Request completed')
    assert record.__dict__['path'] == '/api/v1/alpha'
    assert record.__dict__['status'] == 200
