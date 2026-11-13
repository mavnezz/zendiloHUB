import json
import logging
import sys
from datetime import UTC
from uuid import UUID

from zendilohub.core.infrastructure.system_clock import system_clock
from zendilohub.core.infrastructure.uuid_generator import uuid_generator
from zendilohub.core.logging import JsonFormatter, configure_logging


def test_the_system_clock_tells_utc_time() -> None:
    assert system_clock.now().tzinfo is UTC


def test_ids_are_time_ordered_uuids() -> None:
    first, second = uuid_generator.new_id(), uuid_generator.new_id()
    assert UUID(first).version == 7
    assert first < second


def test_logs_json_lines_with_extra_fields() -> None:
    record = logging.LogRecord('zendilohub.test', logging.WARNING, __file__, 1, 'Hello %s', ('world',), None)
    record.job_id = 'job-1'
    entry = json.loads(JsonFormatter().format(record))

    assert entry['level'] == 'warning'
    assert entry['logger'] == 'zendilohub.test'
    assert entry['message'] == 'Hello world'
    assert entry['job_id'] == 'job-1'
    assert entry['time'].endswith('+00:00')


def test_logs_exceptions() -> None:
    try:
        raise RuntimeError('boom')
    except RuntimeError:
        record = logging.LogRecord('zendilohub.test', logging.ERROR, __file__, 1, 'Failed', (), sys.exc_info())
    entry = json.loads(JsonFormatter().format(record))

    assert 'RuntimeError: boom' in entry['error']


def test_configures_the_root_logger() -> None:
    configure_logging('debug')
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
    assert logging.getLogger('uvicorn.error').propagate
    configure_logging('info')
