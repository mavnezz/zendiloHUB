from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter, Request
from pydantic import BaseModel

from zendilohub.core.domain.app_domain_error import NotFoundError, RateLimitedError
from zendilohub.core.events.integration_events import ActionPerformed
from zendilohub.core.http.access import SESSION_COOKIE, CurrentAdmin, CurrentUser, OptionalUser, Principal, Public
from zendilohub.core.http.audit import Unaudited, audited, note_audit, path_param
from zendilohub.core.http.http_kernel import HttpKernel

ADA = Principal(user_id='u1', email='ada@example.org', role='user', session_id='s1')
GRACE = Principal(user_id='u2', email='grace@example.org', role='admin', session_id='s2')


class TokenGuard:
    async def authenticate(self, session_token: str) -> Principal | None:
        return {'ada': ADA, 'grace': GRACE}.get(session_token)


class NoteMissingError(NotFoundError):
    def __init__(self, note_id: str) -> None:
        super().__init__('note_not_found', f'Note {note_id} not found', {'note_id': note_id})


class SlowDownError(RateLimitedError):
    def __init__(self) -> None:
        super().__init__('slow_down', 'Too many requests', {'retry_after': 30})


class Note(BaseModel):
    text: str


def _router() -> APIRouter:
    router = APIRouter()

    @router.get('/open', dependencies=[Public])
    async def open_route() -> dict[str, str]:
        return {'hello': 'world'}

    @router.get('/maybe')
    async def maybe(principal: OptionalUser) -> dict[str, str | None]:
        return {'user': principal.email if principal else None}

    @router.get('/mine')
    async def mine(principal: CurrentUser) -> dict[str, str]:
        return {'user': principal.email}

    @router.get('/admin')
    async def admin(principal: CurrentAdmin) -> dict[str, str]:
        return {'admin': principal.email}

    @router.post('/notes', dependencies=[Public, audited('note.created')])
    async def create(note: Note, request: Request, _principal: OptionalUser) -> Note:
        note_audit(request, target=note.text, actor_email='someone@example.org')
        return note

    @router.delete(
        '/tenants/{tenant_id}/notes/{note_id}', dependencies=[audited('note.deleted', target=path_param('note_id'))]
    )
    async def delete_note(tenant_id: str, note_id: str, _principal: CurrentUser) -> None:
        pass

    @router.post('/preview', dependencies=[Public, Unaudited])
    async def preview(note: Note) -> Note:
        return note

    @router.get('/notes/{note_id}', dependencies=[Public])
    async def missing(note_id: str) -> None:
        raise NoteMissingError(note_id)

    @router.get('/slow', dependencies=[Public])
    async def slow() -> None:
        raise SlowDownError()

    @router.get('/crash', dependencies=[Public])
    async def crash() -> None:
        raise RuntimeError('boom')

    return router


@pytest.fixture
def kernel() -> HttpKernel:
    kernel = HttpKernel()
    kernel.use_auth_guard(TokenGuard())
    kernel.routes(_router())
    return kernel


def _client(kernel: HttpKernel, session: str | None = None) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=kernel.app, raise_app_exceptions=False)
    cookies = {SESSION_COOKIE: session} if session else None
    return httpx.AsyncClient(transport=transport, base_url='http://zendilohub.test', cookies=cookies)


async def test_applies_the_access_policies(kernel: HttpKernel) -> None:
    async with _client(kernel) as anonymous, _client(kernel, 'ada') as ada, _client(kernel, 'grace') as grace:
        assert (await anonymous.get('/api/v1/open')).json() == {'hello': 'world'}
        assert (await anonymous.get('/api/v1/maybe')).json() == {'user': None}
        assert (await ada.get('/api/v1/maybe')).json() == {'user': 'ada@example.org'}

        response = await anonymous.get('/api/v1/mine')
        assert response.status_code == 401
        assert response.json() == {'error': 'unauthenticated', 'message': 'Login required'}
        assert (await ada.get('/api/v1/mine')).json() == {'user': 'ada@example.org'}

        response = await ada.get('/api/v1/admin')
        assert response.status_code == 403
        assert response.json()['error'] == 'forbidden'
        assert (await grace.get('/api/v1/admin')).json() == {'admin': 'grace@example.org'}


async def test_an_unknown_session_is_anonymous(kernel: HttpKernel) -> None:
    async with _client(kernel, 'mallory') as client:
        assert (await client.get('/api/v1/mine')).status_code == 401


async def test_without_a_guard_nobody_is_logged_in() -> None:
    kernel = HttpKernel()
    kernel.routes(_router())
    async with _client(kernel, 'ada') as client:
        assert (await client.get('/api/v1/mine')).status_code == 401


def test_refuses_routes_without_an_access_policy() -> None:
    router = APIRouter()

    @router.get('/forgotten')
    async def forgotten() -> None:
        pass

    with pytest.raises(ValueError, match='Route GET /forgotten declares no access policy'):
        HttpKernel().routes(router)


async def test_reports_errors_in_one_format(kernel: HttpKernel) -> None:
    async with _client(kernel) as client:
        response = await client.get('/api/v1/notes/42')
        assert response.status_code == 404
        assert response.json() == {
            'error': 'note_not_found',
            'message': 'Note 42 not found',
            'params': {'note_id': '42'},
        }

        response = await client.post('/api/v1/notes', json={'text': 7})
        assert response.status_code == 422
        assert response.json()['error'] == 'invalid_request'
        assert response.json()['details'][0]['field'] == 'text'

        response = await client.get('/api/v1/slow')
        assert response.status_code == 429
        assert response.headers['retry-after'] == '30'

        response = await client.get('/api/v1/nothing-here')
        assert response.status_code == 404
        assert response.json()['error'] == 'not_found'

        response = await client.delete('/api/v1/open')
        assert response.status_code == 405
        assert response.json()['error'] == 'method_not_allowed'

        response = await client.get('/api/v1/crash')
        assert response.status_code == 500
        assert response.json() == {'error': 'internal_error', 'message': 'Internal server error'}


async def test_sets_security_headers(kernel: HttpKernel) -> None:
    async with _client(kernel) as client:
        response = await client.get('/api/v1/open')
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'
    assert 'content-security-policy' not in response.headers


@pytest.mark.parametrize(
    ('headers', 'status'),
    [
        ({'sec-fetch-site': 'cross-site'}, 403),
        ({'sec-fetch-site': 'same-site'}, 403),
        ({'sec-fetch-site': 'same-origin'}, 200),
        ({'origin': 'https://evil.example'}, 403),
        ({'origin': 'http://zendilohub.test'}, 200),
        ({'origin': 'https://print.example.org', 'x-forwarded-host': 'print.example.org'}, 200),
        ({}, 200),
    ],
)
async def test_rejects_cross_site_writes(kernel: HttpKernel, headers: dict[str, str], status: int) -> None:
    async with _client(kernel) as client:
        response = await client.post('/api/v1/notes', json={'text': 'hi'}, headers=headers)
    assert response.status_code == status
    if status == 403:
        assert response.json()['error'] == 'cross_site_request'


async def test_cross_site_reads_are_fine(kernel: HttpKernel) -> None:
    async with _client(kernel) as client:
        assert (await client.get('/api/v1/open', headers={'sec-fetch-site': 'cross-site'})).status_code == 200


async def test_reports_health() -> None:
    kernel = HttpKernel()
    results = {'database': True}

    async def database() -> bool:
        return results['database']

    kernel.add_health_check('database', database)
    async with _client(kernel) as client:
        for path in ('/health', '/api/v1/health'):
            response = await client.get(path)
            assert response.status_code == 200
            assert response.json() == {'status': 'ok', 'checks': {'database': 'ok'}}
        results['database'] = False
        response = await client.get('/health')
        assert response.status_code == 503
        assert response.json() == {'status': 'unavailable', 'checks': {'database': 'down'}}


@pytest.fixture
def web_dir(tmp_path: Path) -> Path:
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'app-123.js').write_text('console.log(1)')
    (tmp_path / 'favicon.svg').write_text('<svg/>')
    (tmp_path / 'index.html').write_text('<html><script>window.x = 1</script><div id="app"></div></html>')
    (tmp_path.parent / 'secret.txt').write_text('secret')
    return tmp_path


async def test_serves_the_web_app(kernel: HttpKernel, web_dir: Path) -> None:
    assert kernel.serve_web_app(web_dir)
    async with _client(kernel) as client:
        response = await client.get('/')
        assert response.status_code == 200
        assert '<div id="app">' in response.text
        assert response.headers['cache-control'] == 'no-cache'
        assert "script-src 'self' 'sha256-" in response.headers['content-security-policy']

        # Client-side routes render the app, too.
        assert '<div id="app">' in (await client.get('/account/usage')).text

        response = await client.get('/assets/app-123.js')
        assert response.text == 'console.log(1)'
        assert response.headers['cache-control'] == 'public, max-age=31536000, immutable'

        response = await client.get('/favicon.svg')
        assert response.text == '<svg/>'
        assert response.headers['cache-control'] == 'no-cache'

        assert 'secret' not in (await client.get('/../secret.txt')).text
        assert 'secret' not in (await client.get('/%2e%2e/secret.txt')).text

        # The API stays JSON.
        assert (await client.get('/api/v1/open')).json() == {'hello': 'world'}
        response = await client.get('/api/v1/unknown')
        assert response.status_code == 404
        assert response.json()['error'] == 'not_found'
        assert (await client.post('/somewhere')).status_code == 404
        # So do discovery documents zendiloHUB does not have (OpenID Connect): missing, not the web app.
        assert (await client.get('/.well-known/openid-configuration')).status_code == 404


def test_serves_nothing_without_a_build(kernel: HttpKernel, tmp_path: Path) -> None:
    assert not kernel.serve_web_app(tmp_path)


async def test_the_api_docs_can_be_turned_off() -> None:
    async with _client(HttpKernel(api_docs=False)) as client:
        assert (await client.get('/api/docs')).status_code == 404
    async with _client(HttpKernel()) as client:
        response = await client.get('/api/docs')
        assert response.status_code == 200
        assert 'content-security-policy' not in response.headers
        assert (await client.get('/api/openapi.json')).json()['info']['title'] == 'zendiloHUB API'


def test_refuses_state_changing_routes_without_an_audit_action() -> None:
    router = APIRouter()

    @router.patch('/unrecorded', dependencies=[Public])
    async def unrecorded() -> None:
        pass

    with pytest.raises(ValueError, match='Route PATCH /unrecorded declares no audit action'):
        HttpKernel().routes(router)


async def test_records_audited_requests(kernel: HttpKernel) -> None:
    recorded: list[ActionPerformed] = []

    async def sink(action: ActionPerformed) -> None:
        recorded.append(action)

    kernel.use_audit_sink(sink)
    async with _client(kernel, 'ada') as ada, _client(kernel) as anonymous:
        assert (await ada.post('/api/v1/notes', json={'text': 'hi'})).status_code == 200
        assert (await ada.post('/api/v1/notes', json={'text': 7})).status_code == 422
        assert (await anonymous.post('/api/v1/notes', json={'text': 'anonymous'})).status_code == 200
        assert (await ada.delete('/api/v1/tenants/t1/notes/n1')).status_code == 200
        assert (await anonymous.delete('/api/v1/tenants/t1/notes/n2')).status_code == 401
        assert (await ada.post('/api/v1/preview', json={'text': 'not recorded'})).status_code == 200

    assert [(a.action, a.actor_id, a.actor_email, a.target, a.succeeded, a.status) for a in recorded] == [
        ('note.created', 'u1', 'ada@example.org', 'hi', True, 200),
        ('note.created', 'u1', 'ada@example.org', None, False, 422),
        ('note.created', None, 'someone@example.org', 'anonymous', True, 200),
        ('note.deleted', 'u1', 'ada@example.org', 'n1', True, 200),
        ('note.deleted', None, None, 'n2', False, 401),
    ]
    assert [a.tenant_id for a in recorded] == [None, None, None, 't1', 't1']
    assert recorded[0].client == '127.0.0.1'


async def test_a_failing_audit_log_does_not_break_the_answer(
    kernel: HttpKernel, caplog: pytest.LogCaptureFixture
) -> None:
    async def sink(_action: ActionPerformed) -> None:
        raise RuntimeError('database down')

    kernel.use_audit_sink(sink)
    async with _client(kernel) as client:
        assert (await client.post('/api/v1/notes', json={'text': 'hi'})).status_code == 200
    assert 'Recording an audited action failed' in caplog.text


async def test_without_an_audit_sink_nothing_is_recorded(kernel: HttpKernel) -> None:
    async with _client(kernel) as client:
        assert (await client.post('/api/v1/notes', json={'text': 'hi'})).status_code == 200
