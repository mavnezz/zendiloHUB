import asyncio
import logging
import os
from pathlib import Path

import pytest

from zendilohub.core.contracts import Slot
from zendilohub.core.infrastructure.secret_key import SecretKey
from zendilohub.core.scheduler import Scheduler


async def test_the_scheduler_runs_jobs_periodically_and_survives_failures(caplog: pytest.LogCaptureFixture) -> None:
    runs: list[str] = []
    each_ran_twice = asyncio.Event()

    def ran(job: str) -> None:
        runs.append(job)
        if runs.count('good') >= 2 and runs.count('bad') >= 2:
            each_ran_twice.set()

    async def good() -> None:
        ran('good')

    async def bad() -> None:
        ran('bad')
        raise RuntimeError('boom')

    scheduler = Scheduler()
    scheduler.every(0.01, 'good', good)
    scheduler.every(0.01, 'bad', bad)
    with caplog.at_level(logging.ERROR):
        scheduler.start()
        # However busy the machine is: a fixed wait is too short now and then.
        await asyncio.wait_for(each_ran_twice.wait(), timeout=10)
        await scheduler.stop()
    assert 'Scheduled job failed' in caplog.text

    # Run by hand (tests, CLI), failures surface.
    runs.clear()
    with pytest.raises(RuntimeError, match='boom'):
        await scheduler.run_all()
    assert runs == ['good', 'bad']


def test_slots_are_provided_once() -> None:
    slot: Slot[str] = Slot('Thing')
    with pytest.raises(RuntimeError, match='No module provides Thing'):
        slot.get()
    slot.provide('it')
    assert slot.get() == 'it'
    with pytest.raises(RuntimeError, match='Thing is already provided'):
        slot.provide('another')


def test_the_secret_key_comes_from_the_environment_or_is_generated_once(tmp_path: Path) -> None:
    assert SecretKey('configured', tmp_path).value == b'configured'
    assert not (tmp_path / 'secret_key').exists()

    generated = SecretKey(None, tmp_path / 'data').value
    assert len(generated) == 64
    assert SecretKey(None, tmp_path / 'data').value == generated
    assert oct(os.stat(tmp_path / 'data' / 'secret_key').st_mode & 0o777) == '0o600'


def test_two_processes_creating_the_key_at_once_share_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_file = tmp_path / 'secret_key'
    real_open = os.open

    def racing_open(path: object, flags: int, mode: int = 0o777) -> int:
        # The other process wins the race just before this one creates the file.
        key_file.write_bytes(b'theirs')
        return real_open(path, flags, mode)  # type: ignore[arg-type]

    monkeypatch.setattr(os, 'open', racing_open)
    assert SecretKey(None, tmp_path).value == b'theirs'
