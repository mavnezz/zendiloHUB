from pathlib import Path
from typing import Any

import pytest
from rq import Worker

from support.app import make_config
from support.services import Services
from zendilohub import worker as worker_module
from zendilohub.core.config import load_config


@pytest.mark.usefixtures('template_database')
async def test_runs_a_task_in_a_short_lived_app(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    services.create_database('test_worker_task', template='zendilohub_template')
    config = make_config(services, tmp_path, 'test_worker_task')
    seen: list[tuple[str, tuple[str, ...]]] = []

    async def run_task(self: Any, name: str, *args: str) -> None:
        seen.append((name, args))

    monkeypatch.setattr('zendilohub.core.application.Application.run_task', run_task)
    try:
        await worker_module._run_task(config, 'processing.process-image', ('image-1',))
    finally:
        services.drop_database('test_worker_task')
    assert seen == [('processing.process-image', ('image-1',))]


def test_run_task_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    async def fake(config: Any, name: str, args: tuple[str, ...]) -> None:
        calls.append((config.port, name, args))

    monkeypatch.setattr(worker_module, '_run_task', fake)
    monkeypatch.setenv('ZENDILOHUB_PORT', '9999')
    worker_module.run_task('a-task', 'x')
    assert calls == [(9999, 'a-task', ('x',))]


def test_the_worker_touches_its_heartbeat_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, services: Services
) -> None:
    heartbeat = tmp_path / 'heartbeat'
    monkeypatch.setattr(worker_module.HeartbeatWorker, 'heartbeat_file', heartbeat)
    started: list[dict[str, Any]] = []

    def work(self: Worker, **kwargs: Any) -> bool:
        started.append({**kwargs, 'idle_wait': self.dequeue_timeout})
        self.heartbeat()
        return True

    monkeypatch.setattr(Worker, 'work', work)
    config = load_config({'ZENDILOHUB_REDIS_URL': services.redis_url})
    assert worker_module.run_worker(config) == 0
    assert heartbeat.exists()
    assert started[0]['with_scheduler'] is True
    # An idle worker beats often enough for the container's health check (120 seconds).
    assert started[0]['idle_wait'] == 45
