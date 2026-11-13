import asyncio
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from .core.application import Application
from .core.config import AppConfig, load_config
from .core.logging import configure_logging
from .providers import providers

USAGE = """Usage: zendilohub <command>

  serve                 Serve the web app and the API (default)
  worker                Process background jobs from the queue
  migrate               Run pending database migrations
  openapi [FILE]        Write the OpenAPI schema (to stdout or FILE)
  <module command>      e.g. make-admin; run `zendilohub help` for the list
"""


class StdOutput:
    def line(self, text: str) -> None:
        sys.stdout.write(f'{text}\n')

    def error(self, text: str) -> None:
        sys.stderr.write(f'{text}\n')


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else 'serve'
    if command in ('-h', '--help'):
        sys.stdout.write(USAGE)
        return 0
    config = load_config(os.environ)
    configure_logging(config.log_level)
    match command:
        case 'serve':
            return asyncio.run(serve(config))
        case 'worker':
            from .worker import run_worker

            return run_worker(config)
        case 'migrate':
            return asyncio.run(migrate(config))
        case 'openapi':
            return write_openapi(config, args[1] if len(args) > 1 else None)
        case _:
            return asyncio.run(run_command(config, args))


async def serve(config: AppConfig) -> int:
    app = Application.create(config, modules=providers)
    await app.start()
    server = uvicorn.Server(
        uvicorn.Config(
            app.http.app,
            host=config.host,
            port=config.port,
            proxy_headers=True,
            forwarded_allow_ips=config.trusted_proxies,
            # Logging is configured by configure_logging; requests are logged at debug level.
            log_config=None,
            access_log=False,
            lifespan='off',
            # Open live streams (SSE) must not delay a restart forever.
            timeout_graceful_shutdown=10,
        )
    )
    try:
        await server.serve()
    finally:
        await app.shutdown()
    return 0


async def migrate(config: AppConfig) -> int:
    app = Application.create(config, modules=providers, role='cli')
    try:
        await app.db.open()
        applied = await app.migrate()
        StdOutput().line(f'Applied {len(applied)} migration(s).')
    finally:
        await app.shutdown()
    return 0


def write_openapi(config: AppConfig, path: str | None) -> int:
    schema = json.dumps(Application.create(config, modules=providers, role='cli').http.app.openapi(), indent=2)
    if path is None:
        sys.stdout.write(f'{schema}\n')
    else:
        Path(path).write_text(f'{schema}\n', 'utf-8')
    return 0


async def run_command(config: AppConfig, argv: Sequence[str]) -> int:
    app = Application.create(config, modules=providers, role='cli')
    try:
        await app.start()
        return await app.run_command([] if argv[0] == 'help' else argv, StdOutput())
    finally:
        await app.shutdown()
