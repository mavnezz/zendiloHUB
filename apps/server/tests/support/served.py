import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn

from .app import AppUnderTest


@asynccontextmanager
async def served(app: AppUnderTest) -> AsyncIterator[str]:
    """The app on a real port, for what httpx's in-process transport cannot do (event streams, WebSockets)."""
    server = uvicorn.Server(uvicorn.Config(app.app.http.app, host='127.0.0.1', port=0, lifespan='off', log_config=None))
    task = asyncio.create_task(server.serve())
    async with asyncio.timeout(5):
        while not server.started:  # noqa: ASYNC110 (uvicorn offers no event to wait on)
            await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        await task
