from collections.abc import AsyncIterator

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from zendilohub.core.domain.http_fetch import FetchBlockedError, FetchFailedError
from zendilohub.core.infrastructure import public_fetcher
from zendilohub.core.infrastructure.public_fetcher import AiohttpPublicFetcher, PublicResolver, is_public


@pytest.fixture
async def api() -> AsyncIterator[str]:
    async def orders(request: web.Request) -> web.Response:
        if request.method == 'POST':
            return web.json_response({'received': await request.json()})
        return web.json_response({'order': request.query.get('number'), 'status': 'shipped'})

    async def big(request: web.Request) -> web.Response:
        return web.Response(body=b'x' * 2048)

    async def moved(request: web.Request) -> web.Response:
        raise web.HTTPFound('http://169.254.169.254/latest/meta-data')

    app = web.Application()
    app.router.add_route('*', '/orders', orders)
    app.router.add_get('/big', big)
    app.router.add_get('/moved', moved)
    async with TestServer(app) as server:
        yield str(server.make_url('')).rstrip('/')


def test_knows_public_addresses() -> None:
    assert is_public('93.184.215.14')
    for address in ('127.0.0.1', '10.0.0.5', '172.18.0.2', '192.168.1.9', '169.254.169.254', '::1', 'fd00::1'):
        assert not is_public(address), address


async def test_refuses_our_own_network() -> None:
    fetcher = AiohttpPublicFetcher()
    for url in ('http://127.0.0.1:8080/api', 'http://[::1]/', 'http://localhost/', 'ftp://example.org/x', 'https:///x'):
        with pytest.raises(FetchBlockedError):
            await fetcher.fetch('GET', url)
    with pytest.raises(OSError, match='not a public address'):
        await PublicResolver().resolve('localhost', 80)


async def test_asks_public_services(api: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # The test server runs on localhost: treat it as public for this test.
    monkeypatch.setattr(public_fetcher, 'is_public', lambda address: True)
    fetcher = AiohttpPublicFetcher(max_bytes=1024)

    found = await fetcher.fetch('GET', f'{api}/orders', query={'number': 'A-17'})
    assert (found.status, found.content_type) == (200, 'application/json')
    assert found.body == b'{"order": "A-17", "status": "shipped"}'
    posted = await fetcher.fetch('POST', f'{api}/orders', json={'number': 'A-17'})
    assert posted.body == b'{"received": {"number": "A-17"}}'
    # Redirects are not followed (they could lead into the own network).
    assert (await fetcher.fetch('GET', f'{api}/moved')).status == 302
    with pytest.raises(FetchFailedError, match='larger than 1024 bytes'):
        await fetcher.fetch('GET', f'{api}/big')
    with pytest.raises(FetchFailedError):
        await AiohttpPublicFetcher(timeout=1).fetch('GET', 'http://127.0.0.1:9/nothing')
