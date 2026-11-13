from typing import Any

from support.app import AppUnderTest
from support.identity import PASSWORD, logged_in, make_admin
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of


def _log(response_json: dict[str, Any]) -> list[tuple[str, str | None, str | None, bool]]:
    return [
        (entry['action'], entry['actor_email'], entry['target'], entry['succeeded']) for entry in response_json['items']
    ]


async def test_records_who_changed_what_in_the_organization(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    bob_id = await user_id_of(bob)
    await ada.patch(f'{TENANTS}/{tenant}', json={'name': 'Acme AG'})
    await ada.patch(f'{TENANTS}/{tenant}/members/{bob_id}', json={'role': 'manager'})
    await bob.patch(f'{TENANTS}/{tenant}', json={'name': 'Not allowed'})
    await ada.delete(f'{TENANTS}/{tenant}/members/{bob_id}')

    response = await ada.get(f'{TENANTS}/{tenant}/audit-log')

    assert response.status_code == 200, response.text
    assert _log(response.json()) == [
        ('member.removed', 'ada@example.org', 'bob@example.org', True),
        ('tenant.updated', 'bob@example.org', None, False),
        ('member.role_changed', 'ada@example.org', 'bob@example.org: manager', True),
        ('tenant.updated', 'ada@example.org', None, True),
        ('invitation.accepted', 'bob@example.org', 'bob@example.org', True),
        ('invitation.sent', 'ada@example.org', 'bob@example.org: agent', True),
        ('tenant.created', 'ada@example.org', 'Acme GmbH', True),
    ]
    entry = response.json()['items'][1]
    assert entry['status'] == 403
    assert entry['tenant_id'] == tenant
    assert response.json()['total'] == 7
    page = (await ada.get(f'{TENANTS}/{tenant}/audit-log', params={'offset': 5, 'limit': 1})).json()
    assert _log(page) == [('invitation.sent', 'ada@example.org', 'bob@example.org: agent', True)]


async def test_shows_the_log_to_owners_and_admins_only(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    manager = await member_of(app, tenant, ada, 'manager@example.org', 'manager')
    admin = await member_of(app, tenant, ada, 'admin@example.org', 'admin')
    other = await logged_in(app, 'other@example.org')

    assert (await manager.get(f'{TENANTS}/{tenant}/audit-log')).status_code == 403
    assert (await admin.get(f'{TENANTS}/{tenant}/audit-log')).status_code == 200
    assert (await other.get(f'{TENANTS}/{tenant}/audit-log')).status_code == 404


async def test_keeps_the_organizations_apart(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    acme = await create_tenant(ada, 'Acme')
    beta = await create_tenant(ada, 'Beta')
    await ada.patch(f'{TENANTS}/{beta}', json={'name': 'Beta AG'})

    acme_log = _log((await ada.get(f'{TENANTS}/{acme}/audit-log')).json())

    assert acme_log == [('tenant.created', 'ada@example.org', 'Acme', True)]


async def test_records_logins_and_account_changes_for_the_platform(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    await app.new_client().post('/api/v1/auth/login', json={'email': 'Ada@Example.org', 'password': 'wrong'})
    await ada.post('/api/v1/account/password', json={'current_password': PASSWORD, 'new_password': 'a new password'})
    await ada.post('/api/v1/auth/logout')
    root = await logged_in(app, 'root@example.org')
    await make_admin(app, 'root@example.org')

    page = (await root.get('/api/v1/admin/audit-log')).json()

    actions = [(entry['action'], entry['actor_email'], entry['succeeded']) for entry in page['items']]
    assert ('auth.login', 'ada@example.org', False) in actions
    assert ('account.password_changed', 'ada@example.org', True) in actions
    assert ('auth.logout', 'ada@example.org', True) in actions
    assert ('auth.registration_confirmed', 'root@example.org', True) in actions
    # Ada logged out.
    assert (await ada.get('/api/v1/admin/audit-log')).status_code == 401
    eve = await logged_in(app, 'eve@example.org')
    assert (await eve.get('/api/v1/admin/audit-log')).status_code == 403


async def test_platform_administrators_filter_by_organization(app: AppUnderTest) -> None:
    root = await logged_in(app, 'root@example.org')
    await make_admin(app, 'root@example.org')
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    await root.patch(f'/api/v1/admin/tenants/{tenant}', json={'status': 'suspended'})

    page = (await root.get('/api/v1/admin/audit-log', params={'tenant_id': tenant})).json()

    assert _log(page) == [
        ('admin.tenant_status_changed', 'root@example.org', 'suspended', True),
        ('tenant.created', 'ada@example.org', 'Acme GmbH', True),
    ]
    assert (await root.get('/api/v1/admin/audit-log', params={'tenant_id': 'nope'})).status_code == 422


async def test_forgets_deleted_organizations_and_the_addresses_of_deleted_accounts(app: AppUnderTest) -> None:
    root = await logged_in(app, 'root@example.org')
    await make_admin(app, 'root@example.org')
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    await ada.patch(f'{TENANTS}/{tenant}', json={'name': 'Acme AG'})
    await ada.delete(f'{TENANTS}/{tenant}')

    after_deletion = _log((await root.get('/api/v1/admin/audit-log', params={'tenant_id': tenant})).json())
    # Only the deletion itself stays, so the platform knows who deleted the organization.
    assert after_deletion == [('tenant.deleted', 'ada@example.org', None, True)]

    await ada.post('/api/v1/account/delete', json={'password': PASSWORD})
    entries = (await root.get('/api/v1/admin/audit-log')).json()['items']
    assert [e for e in entries if e['actor_email'] == 'ada@example.org'] == []
    assert any(entry['action'] == 'account.deleted' and entry['actor_email'] is None for entry in entries)


async def test_purges_entries_after_the_retention_period(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    app.clock.advance(days=366)
    # The session expired meanwhile.
    ada = app.new_client()
    await ada.post('/api/v1/auth/login', json={'email': 'ada@example.org', 'password': PASSWORD})
    await ada.patch(f'{TENANTS}/{tenant}', json={'name': 'Acme AG'})

    await app.app.context.scheduler.run_all()

    log = _log((await ada.get(f'{TENANTS}/{tenant}/audit-log')).json())
    assert log == [('tenant.updated', 'ada@example.org', None, True)]
