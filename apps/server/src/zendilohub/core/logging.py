import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has; everything else was passed as `extra=` and is logged as a field.
_STANDARD = set(logging.makeLogRecord({}).__dict__) | {'message', 'asctime', 'taskName', 'color_message'}


class JsonFormatter(logging.Formatter):
    """One JSON object per line on stdout, like pino in the TypeScript projects."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            'time': datetime.fromtimestamp(record.created, UTC).isoformat(timespec='milliseconds'),
            'level': record.levelname.lower(),
            'logger': record.name,
            'message': record.getMessage(),
        }
        entry |= {key: value for key, value in record.__dict__.items() if key not in _STANDARD and key[0] != '_'}
        if record.exc_info:
            entry['error'] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for name in ('uvicorn', 'uvicorn.error', 'rq.worker'):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
