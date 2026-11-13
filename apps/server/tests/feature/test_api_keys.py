import httpx
import pytest

from support.app import AppUnderTest
from support.identity import logged_in, make_admin
from support.tenancy import TENANTS, create_tenant, member_of
from zendilohub.core.domain.rate_limiter import RateLimit
from zendilohub.modules.tenancy.application.commands import api_keys


async def setup(app: AppUnderTest) -> tuple[httpx.AsyncClient, str, str]:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    return ada, tenant, f'{TENANTS}/{tenant}/api-keys'


READING = ['members.view', 'audit.view']


async def created_key(
    owner: httpx.AsyncClient, base: str, permissions: list[str] = READING, name: str = 'CRM sync'
) -> str:
    response = await owner.post(base, json={'name': name, 'permissions': permissions})
    assert response.status_code == 201, response.text
    return str(response.json()['key'])


def with_key(app: AppUnderTest, key: str) -> httpx.AsyncClient:
    """Another system: no session, only the key."""
    client = app.new_client()
    client.headers['Authorization'] = f'Bearer {key}'
    return client


async def test_creates_keys_that_are_shown_once(app: AppUnderTest) -> None:
    ada, tenant, base = await setup(app)
    manager = await member_of(app, tenant, ada, 'max@example.org', 'manager')

    created = await ada.post(base, json={'name': ' CRM sync ', 'permissions': ['audit.view', 'members.view']})
    assert created.status_code == 201, created.text
    key = created.json()['key']
    assert key.startswith('zhk_')
    assert len(key) > 40
    api_key = created.json()['api_key']
    assert (api_key['name'], api_key['permissions'], api_key['start'], api_key['last_used_at']) == (
        'CRM sync',
        READING,
        key[:10],
        None,
    )
    listed = await ada.get(base)
    assert [(each['id'], each['permissions']) for each in listed.json()] == [(api_key['id'], READING)]
    assert key not in listed.text
    assert (await manager.get(base)).status_code == 403
    assert (await manager.post(base, json={'name': 'x', 'permissions': READING})).status_code == 403

    # Nothing that needs a person or an owner, and not nothing at all.
    for permission in ('tenant.delete', 'members.manage', 'recordings.delete', 'owner'):
        assert (await ada.post(base, json={'name': 'Root', 'permissions': [permission]})).status_code == 422
    for body, field in (
        ({'name': '   ', 'permissions': READING}, 'name'),
        ({'name': 'None', 'permissions': []}, 'permissions'),
    ):
        refused = await ada.post(base, json=body)
        assert (refused.status_code, refused.json()['error'], refused.json()['params']) == (
            422,
            'invalid_api_key',
            {'field': field},
        )
    for index in range(19):
        await created_key(ada, base, name=f'Key {index}')
    too_many = await ada.post(base, json={'name': 'One more', 'permissions': READING})
    assert (too_many.status_code, too_many.json()['error']) == (409, 'api_key_limit')


async def test_a_key_acts_in_its_organization_with_its_permissions(app: AppUnderTest) -> None:
    ada, tenant, base = await setup(app)
    other = await create_tenant(ada, 'Other GmbH')
    reader = with_key(app, await created_key(ada, base))
    team = with_key(app, await created_key(ada, base, ['members.view'], name='Directory sync'))

    assert (await reader.get(f'{TENANTS}/{tenant}/audit-log')).status_code == 200
    own = (await reader.get(f'{TENANTS}/{tenant}')).json()
    assert (own['role'], own['permissions']) == (None, READING)
    denied = await team.get(f'{TENANTS}/{tenant}/audit-log')
    assert (denied.status_code, denied.json()['error'], denied.json()['params']) == (
        403,
        'permission_denied',
        {'permission': 'audit.view'},
    )
    assert (await team.get(f'{TENANTS}/{tenant}/members')).status_code == 200

    # Nothing outside its organization, and nothing that needs an account.
    assert (await team.get(f'{TENANTS}/{other}/members')).status_code == 404
    assert (await team.get(TENANTS)).status_code == 401
    assert (await team.get('/api/v1/account')).status_code == 401


async def test_changes_the_name_and_permissions_of_a_key(app: AppUnderTest) -> None:
    ada, tenant, base = await setup(app)
    client = with_key(app, await created_key(ada, base, ['members.view']))
    [listed] = (await ada.get(base)).json()
    audit_log = f'{TENANTS}/{tenant}/audit-log'
    assert (await client.get(audit_log)).status_code == 403

    changed = await ada.patch(f'{base}/{listed["id"]}', json={'name': 'Reports', 'permissions': ['audit.view']})
    assert changed.status_code == 200, changed.text
    assert (changed.json()['name'], changed.json()['permissions'], changed.json()['start']) == (
        'Reports',
        ['audit.view'],
        listed['start'],
    )
    assert (await client.get(audit_log)).status_code == 200
    assert (await client.get(f'{TENANTS}/{tenant}/members')).status_code == 403

    refused = await ada.patch(f'{base}/{listed["id"]}', json={'name': 'Reports', 'permissions': []})
    assert (refused.status_code, refused.json()['params']) == (422, {'field': 'permissions'})
    missing = await ada.patch(f'{base}/{"0" * 8}-0000-4000-8000-{"0" * 12}', json={'name': 'x', 'permissions': READING})
    assert (missing.status_code, missing.json()['error']) == (404, 'api_key_not_found')
    log = (await ada.get(f'{TENANTS}/{tenant}/audit-log')).json()['items']
    updates = [(each['target'], each['succeeded']) for each in log if each['action'] == 'api_key.updated']
    assert updates[-1] == ('Reports', True)


async def test_people_manage_the_organization_the_team_and_the_keys(app: AppUnderTest) -> None:
    ada, tenant, base = await setup(app)
    admin_key = with_key(app, await created_key(ada, base, READING))
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    bob_id = str((await bob.get('/api/v1/account')).json()['id'])

    for method, path, body in (
        ('GET', base, None),
        ('POST', base, {'name': 'More', 'permissions': READING}),
        ('PATCH', f'{base}/{bob_id}', {'name': 'More', 'permissions': READING}),
        ('PATCH', f'{TENANTS}/{tenant}', {'name': 'Taken over'}),
        ('POST', f'{TENANTS}/{tenant}/invitations', {'email': 'eve@example.org', 'role': 'admin'}),
        ('PATCH', f'{TENANTS}/{tenant}/members/{bob_id}', {'role': 'admin'}),
        ('DELETE', f'{TENANTS}/{tenant}/members/{bob_id}', None),
    ):
        response = await admin_key.request(method, path, json=body)
        assert (response.status_code, response.json()['error']) == (403, 'people_only'), (method, path)
    assert (await admin_key.get(f'{TENANTS}/{tenant}/members')).status_code == 200


async def test_deleted_keys_and_suspended_organizations_are_locked_out(app: AppUnderTest) -> None:
    ada, tenant, base = await setup(app)
    key = await created_key(ada, base)
    client = with_key(app, key)
    audit_log = f'{TENANTS}/{tenant}/audit-log'
    assert (await client.get(audit_log)).status_code == 200
    assert (await with_key(app, key[:-1] + 'x').get(audit_log)).status_code == 401
    assert (await with_key(app, 'not-a-key').get(audit_log)).status_code == 401

    root = await logged_in(app, 'root@example.org')
    await make_admin(app, 'root@example.org')
    await root.patch(f'/api/v1/admin/tenants/{tenant}', json={'status': 'suspended'})
    assert (await client.get(audit_log)).status_code == 401
    await root.patch(f'/api/v1/admin/tenants/{tenant}', json={'status': 'active'})
    assert (await client.get(audit_log)).status_code == 200

    [listed] = (await ada.get(base)).json()
    assert (await ada.delete(f'{base}/{listed["id"]}')).status_code == 204
    assert (await ada.delete(f'{base}/{listed["id"]}')).status_code == 404
    assert (await client.get(audit_log)).status_code == 401


async def test_records_when_a_key_was_last_used(app: AppUnderTest) -> None:
    ada, tenant, base = await setup(app)
    client = with_key(app, await created_key(ada, base))
    audit_log = f'{TENANTS}/{tenant}/audit-log'

    await client.get(audit_log)
    first = app.clock.now()
    assert (await ada.get(base)).json()[0]['last_used_at'] == first.isoformat().replace('+00:00', 'Z')
    app.clock.advance(seconds=30)
    await client.get(audit_log)
    assert (await ada.get(base)).json()[0]['last_used_at'] == first.isoformat().replace('+00:00', 'Z')
    app.clock.advance(seconds=31)
    await client.get(audit_log)
    assert (await ada.get(base)).json()[0]['last_used_at'] == app.clock.now().isoformat().replace('+00:00', 'Z')


async def test_limits_the_requests_per_key(app: AppUnderTest, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_keys, 'REQUESTS', RateLimit('tenancy.api-key-requests', limit=2, window_seconds=60))
    ada, tenant, base = await setup(app)
    client = with_key(app, await created_key(ada, base))
    audit_log = f'{TENANTS}/{tenant}/audit-log'

    assert [(await client.get(audit_log)).status_code for _ in range(3)] == [200, 200, 429]
    # The session of a person is not limited by the keys.
    assert (await ada.get(audit_log)).status_code == 200


async def test_keys_go_with_the_organization(app: AppUnderTest) -> None:
    ada, tenant, base = await setup(app)
    await created_key(ada, base)
    assert (await ada.delete(f'{TENANTS}/{tenant}')).status_code == 204
    async with app.app.db.connection() as connection:
        left = await (await connection.execute('SELECT count(*) AS n FROM api_keys')).fetchone()
    assert left == {'n': 0}


async def test_documents_only_what_keys_can_use(app: AppUnderTest) -> None:
    reference = await app.client.get('/api/reference/openapi.json')
    assert reference.status_code == 200
    schema = reference.json()
    paths = schema['paths']
    assert schema['info']['title'] == 'zendiloHUB API'
    assert 'Authorization: Bearer zhk_' in schema['info']['description']
    assert set(paths['/api/v1/tenants/{tenant_id}/audit-log']) == {'get'}
    # Nothing for people only, nothing outside an organization.
    assert '/api/v1/tenants/{tenant_id}/invitations' not in paths
    assert '/api/v1/tenants/{tenant_id}/api-keys' not in paths
    assert set(paths['/api/v1/tenants/{tenant_id}']) == {'get'}
    assert not [path for path in paths if path.startswith(('/api/v1/admin', '/api/v1/auth'))]
    schemas = schema['components']['schemas']
    assert 'AuditPageResponse' in schemas
    assert 'AdminTenantResponse' not in schemas
    assert 'API key' in schema['components']['securitySchemes']

    page = await app.client.get('/api/reference')
    assert page.status_code == 200
    assert '/api/reference/openapi.json' in page.text
