import pytest

from support.app import AppUnderTest
from support.identity import logged_in
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of


async def test_lists_the_built_in_roles(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)

    roles = (await ada.get(f'{TENANTS}/{tenant}/roles')).json()

    assert [role['id'] for role in roles['roles']] == ['owner', 'admin', 'manager', 'agent']
    assert roles['roles'][0] == {
        'id': 'owner',
        'name': None,
        'description': '',
        'builtin': True,
        'permissions': roles['permissions'],
        'member_count': 1,
    }
    assert roles['owner_only'] == ['tenant.delete', 'members.assign_owner']
    assert (await app.client.get(f'{TENANTS}/{tenant}/roles')).status_code == 401


async def test_members_get_what_their_own_role_allows(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'

    created = await ada.post(
        f'{base}/roles',
        json={'name': ' Team lead ', 'description': 'Runs a team', 'permissions': ['queues.manage', 'members.view']},
    )
    assert created.status_code == 201, created.text
    lead = created.json()
    assert lead['name'] == 'Team lead'
    assert lead['permissions'] == ['members.view', 'queues.manage']

    bob = await member_of(app, tenant, ada, 'bob@example.org', lead['id'])
    own = (await bob.get(f'{base}')).json()
    assert own['role'] == lead['id']
    assert own['permissions'] == ['members.view', 'queues.manage']
    assert (await bob.get(f'{base}/queues')).status_code == 200
    assert (await bob.post(f'{base}/queues', json={'name': 'Support'})).status_code == 201
    assert (await bob.get(f'{base}/audit-log')).status_code == 403

    # Changing the role changes what its members may do at once.
    changed = await ada.patch(
        f'{base}/roles/{lead["id"]}', json={'name': 'Lead', 'permissions': ['members.view', 'audit.view']}
    )
    assert changed.json()['member_count'] == 1
    assert (await bob.get(f'{base}/audit-log')).status_code == 200
    assert (await bob.post(f'{base}/queues', json={'name': 'Billing'})).status_code == 403
    assert (await bob.get(TENANTS)).json()[0]['permissions'] == ['members.view', 'audit.view']

    # A role in use stays; once nobody has it, it can go.
    assert (await ada.delete(f'{base}/roles/{lead["id"]}')).json()['error'] == 'role_in_use'
    bob_id = await user_id_of(bob)
    assert (await ada.patch(f'{base}/members/{bob_id}', json={'role': 'agent'})).status_code == 200
    assert (await ada.delete(f'{base}/roles/{lead["id"]}')).status_code == 204
    assert [role['id'] for role in (await ada.get(f'{base}/roles')).json()['roles']][-1] == 'agent'

    entries = (await ada.get(f'{base}/audit-log')).json()['items']
    assert {'role.created', 'role.updated', 'role.deleted'} <= {entry['action'] for entry in entries}


async def test_nobody_hands_out_more_than_they_may_do(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    seer = (await ada.post(f'{base}/roles', json={'name': 'Seer', 'permissions': ['queues.all']})).json()
    cleo = await member_of(app, tenant, ada, 'cleo@example.org', 'admin')
    dan = await member_of(app, tenant, ada, 'dan@example.org', seer['id'])
    dan_id = await user_id_of(dan)

    # Admins may not see every queue, so they neither make, change, hand out nor take away such a role.
    refused = await cleo.post(f'{base}/roles', json={'name': 'All', 'permissions': ['queues.all']})
    assert refused.json()['error'] == 'role_exceeds_own'
    assert (await cleo.patch(f'{base}/roles/{seer["id"]}', json={'name': 'X', 'permissions': ['audit.view']})).json()[
        'error'
    ] == 'role_exceeds_own'
    assert (await cleo.delete(f'{base}/roles/{seer["id"]}')).json()['error'] == 'role_exceeds_own'
    invite = await cleo.post(f'{base}/invitations', json={'email': 'eve@example.org', 'role': seer['id']})
    assert invite.json()['error'] == 'role_exceeds_own'
    assert (await cleo.patch(f'{base}/members/{dan_id}', json={'role': 'agent'})).json()['error'] == 'role_exceeds_own'
    assert (await cleo.delete(f'{base}/members/{dan_id}')).json()['error'] == 'role_exceeds_own'
    # Dan may leave on his own, though.
    assert (await dan.delete(f'{base}/members/{dan_id}')).status_code == 204


@pytest.mark.parametrize(
    ('body', 'code'),
    [
        ({'name': ' ', 'permissions': ['audit.view']}, 'invalid_role'),
        ({'name': 'Deleter', 'permissions': ['tenant.delete']}, 'invalid_role'),
        ({'name': 'Admin', 'permissions': ['audit.view']}, 'role_name_taken'),
    ],
)
async def test_checks_roles(app: AppUnderTest, body: dict[str, object], code: str) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    assert (await ada.post(f'{base}/roles', json={'name': 'admin', 'permissions': ['members.view']})).status_code == 201

    assert (await ada.post(f'{base}/roles', json=body)).json()['error'] == code


async def test_refuses_unknown_roles_and_too_many(app: AppUnderTest, monkeypatch: pytest.MonkeyPatch) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    unknown = '0196f3c0-0000-7000-8000-000000000009'

    invite = await ada.post(f'{base}/invitations', json={'email': 'eve@example.org', 'role': 'boss'})
    assert invite.json()['error'] == 'role_not_found'
    invite = await ada.post(f'{base}/invitations', json={'email': 'eve@example.org', 'role': unknown})
    assert invite.json()['error'] == 'role_not_found'
    assert (await ada.patch(f'{base}/roles/{unknown}', json={'name': 'X', 'permissions': ['audit.view']})).json()[
        'error'
    ] == 'role_not_found'
    assert (await ada.delete(f'{base}/roles/{unknown}')).json()['error'] == 'role_not_found'
    first = (await ada.post(f'{base}/roles', json={'name': 'One', 'permissions': ['audit.view']})).json()
    await ada.post(f'{base}/roles', json={'name': 'Two', 'permissions': ['audit.view']})
    renamed = await ada.patch(f'{base}/roles/{first["id"]}', json={'name': 'two', 'permissions': ['audit.view']})
    assert renamed.json()['error'] == 'role_name_taken'

    monkeypatch.setattr('zendilohub.modules.tenancy.application.commands.roles.ROLES_MAX', 2)
    assert (await ada.post(f'{base}/roles', json={'name': 'Three', 'permissions': ['audit.view']})).json()[
        'error'
    ] == 'role_limit'
