import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from support.services import Services
from zendilohub import main as entry


@pytest.fixture
def environment(services: Services, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    services.create_database('test_main')
    monkeypatch.setenv('ZENDILOHUB_DATABASE_URL', services.database('test_main'))
    monkeypatch.setenv('ZENDILOHUB_REDIS_URL', services.redis_url)
    monkeypatch.setenv('ZENDILOHUB_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('ZENDILOHUB_LOG_LEVEL', 'warning')
    yield
    services.drop_database('test_main')


def test_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert entry.main(['--help']) == 0
    assert 'Usage: zendilohub <command>' in capsys.readouterr().out


def test_writes_the_openapi_schema(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert entry.main(['openapi']) == 0
    assert json.loads(capsys.readouterr().out)['info']['title'] == 'zendiloHUB API'

    target = tmp_path / 'openapi.json'
    assert entry.main(['openapi', str(target)]) == 0
    assert json.loads(target.read_text())['openapi'].startswith('3.')


@pytest.mark.usefixtures('environment')
def test_migrates(capsys: pytest.CaptureFixture[str]) -> None:
    assert entry.main(['migrate']) == 0
    assert 'migration(s)' in capsys.readouterr().out


@pytest.mark.usefixtures('environment')
def test_runs_module_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert entry.main(['help']) == 1
    assert 'Available commands:' in capsys.readouterr().err
    assert entry.main(['frobnicate']) == 1
    assert 'Unknown command "frobnicate".' in capsys.readouterr().err


@pytest.mark.usefixtures('environment')
def test_serves_until_uvicorn_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[uvicorn.Config] = []

    async def serve(server: uvicorn.Server) -> None:
        started.append(server.config)

    monkeypatch.setattr(uvicorn.Server, 'serve', serve)
    assert entry.main([]) == 0
    assert started[0].port == 8080
    assert started[0].proxy_headers
    assert started[0].access_log is False


def test_output_writes_to_stdout_and_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    output = entry.StdOutput()
    output.line('out')
    output.error('err')
    captured = capsys.readouterr()
    assert captured.out == 'out\n'
    assert captured.err == 'err\n'
