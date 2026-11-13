from typing import Any

import httpx
import pytest

from support.app import AppUnderTest
from support.identity import logged_in
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of

FULL = ['view', 'create', 'note', 'reply', 'edit', 'assign', 'move']


async def organization(app: AppUnderTest) -> tuple[httpx.AsyncClient, str, str]:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    return ada, tenant, f'{TENANTS}/{tenant}'


async def created(client: httpx.AsyncClient, path: str, **body: Any) -> dict[str, Any]:
    response = await client.post(path, json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_manages_queues(app: AppUnderTest) -> None:
    ada, _tenant, base = await organization(app)

    support = await created(ada, f'{base}/queues', name='  Support   desk ', description=' First contact ')
    await created(ada, f'{base}/queues', name='Billing')

    assert (support['name'], support['description'], support['rights']) == ('Support desk', 'First contact', [])
    # The owner sees every queue with every right (queues.all).
    listed = (await ada.get(f'{base}/queues')).json()
    assert [(each['name'], each['rights']) for each in listed] == [('Billing', FULL), ('Support desk', FULL)]

    taken = await ada.post(f'{base}/queues', json={'name': 'support DESK'})
    assert (taken.status_code, taken.json()['error']) == (409, 'queue_name_taken')
    empty = await ada.post(f'{base}/queues', json={'name': '   '})
    assert (empty.status_code, empty.json()['error'], empty.json()['params']) == (
        422,
        'invalid_queue',
        {'field': 'name'},
    )

    renamed = await ada.patch(f'{base}/queues/{support["id"]}', json={'name': 'Support'})
    assert (renamed.status_code, renamed.json()['name'], renamed.json()['description']) == (200, 'Support', '')
    clash = await ada.patch(f'{base}/queues/{support["id"]}', json={'name': 'billing'})
    assert clash.json()['error'] == 'queue_name_taken'

    assert (await ada.delete(f'{base}/queues/{support["id"]}')).status_code == 204
    assert [each['name'] for each in (await ada.get(f'{base}/queues')).json()] == ['Billing']
    missing = await ada.delete(f'{base}/queues/{support["id"]}')
    assert (missing.status_code, missing.json()['error']) == (404, 'queue_not_found')

    log = (await ada.get(f'{base}/audit-log')).json()['items']
    assert [(each['action'], each['target'], each['succeeded']) for each in log[:4]] == [
        ('queue.deleted', None, False),
        ('queue.deleted', 'Support', True),
        ('queue.updated', None, False),
        ('queue.updated', 'Support', True),
    ]


async def test_groups_have_members_of_the_organization(app: AppUnderTest) -> None:
    ada, tenant, base = await organization(app)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    bob_id = await user_id_of(bob)
    ada_id = await user_id_of(ada)
    stranger = await logged_in(app, 'eve@example.org')

    group = await created(ada, f'{base}/groups', name='1st level')
    assert group['member_ids'] == []

    changed = await ada.put(f'{base}/groups/{group["id"]}/members', json={'user_ids': [bob_id, ada_id, bob_id]})
    assert changed.status_code == 200, changed.text
    assert changed.json()['member_ids'] == sorted([ada_id, bob_id])

    outsider = await ada.put(
        f'{base}/groups/{group["id"]}/members', json={'user_ids': [bob_id, await user_id_of(stranger)]}
    )
    assert (outsider.status_code, outsider.json()['error']) == (422, 'not_a_member')
    assert [each['member_ids'] for each in (await ada.get(f'{base}/groups')).json()] == [sorted([ada_id, bob_id])]

    taken = await ada.post(f'{base}/groups', json={'name': '1ST LEVEL'})
    assert (taken.status_code, taken.json()['error']) == (409, 'group_name_taken')
    renamed = await ada.patch(f'{base}/groups/{group["id"]}', json={'name': 'First level', 'description': 'Phone'})
    assert (renamed.json()['name'], renamed.json()['description']) == ('First level', 'Phone')

    # Leaving the organization means leaving its groups.
    assert (await ada.delete(f'{base}/members/{bob_id}')).status_code == 204
    assert (await ada.get(f'{base}/groups')).json()[0]['member_ids'] == [ada_id]

    assert (await ada.delete(f'{base}/groups/{group["id"]}')).status_code == 204
    assert (await ada.get(f'{base}/groups')).json() == []
    missing = await ada.patch(f'{base}/groups/{group["id"]}', json={'name': 'x'})
    assert (missing.status_code, missing.json()['error']) == (404, 'group_not_found')


async def test_rights_add_up_over_the_groups_of_a_person(app: AppUnderTest) -> None:
    ada, tenant, base = await organization(app)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    bob_id = await user_id_of(bob)
    support = await created(ada, f'{base}/queues', name='Support')
    billing = await created(ada, f'{base}/queues', name='Billing')
    await created(ada, f'{base}/queues', name='Sales')
    first = await created(ada, f'{base}/groups', name='1st level')
    tech = await created(ada, f'{base}/groups', name='Tech')
    for group in (first, tech):
        await ada.put(f'{base}/groups/{group["id"]}/members', json={'user_ids': [bob_id]})

    async def grant(group: dict[str, Any], queue: dict[str, Any], rights: list[str]) -> httpx.Response:
        return await ada.put(
            f'{base}/queue-rights', json={'group_id': group['id'], 'queue_id': queue['id'], 'rights': rights}
        )

    contributing = await grant(first, support, ['note', 'view', 'note'])
    assert contributing.json() == {
        'group_id': first['id'],
        'queue_id': support['id'],
        'rights': ['view', 'note'],
        'preset': 'contribute',
    }
    await grant(tech, support, ['view', 'reply'])
    await grant(first, billing, ['view'])

    # Bob sees what his groups allow, the union of their rights; nothing of Sales.
    seen = {each['name']: each['rights'] for each in (await bob.get(f'{base}/queues')).json()}
    assert seen == {'Billing': ['view'], 'Support': ['view', 'note', 'reply']}

    matrix = (await ada.get(f'{base}/queue-rights')).json()
    assert matrix['rights'] == FULL
    assert matrix['presets']['work'] == ['view', 'create', 'note', 'reply', 'edit']
    assert len(matrix['grants']) == 3
    assert {each['preset'] for each in matrix['grants']} == {'contribute', 'read', None}

    # No rights take the grant away; rights without `view` do not show the queue.
    await grant(first, billing, [])
    await grant(tech, support, ['reply'])
    await grant(first, support, [])
    assert (await bob.get(f'{base}/queues')).json() == []
    assert len((await ada.get(f'{base}/queue-rights')).json()['grants']) == 1

    wrong = await grant(first, support, ['fly'])
    assert wrong.status_code == 422
    other = await create_tenant(ada, 'Other GmbH')
    foreign = await created(ada, f'{TENANTS}/{other}/queues', name='Elsewhere')
    unknown = await grant(first, foreign, ['view'])
    assert (unknown.status_code, unknown.json()['error']) == (404, 'queue_not_found')
    no_group = await ada.put(
        f'{base}/queue-rights', json={'group_id': foreign['id'], 'queue_id': support['id'], 'rights': ['view']}
    )
    assert (no_group.status_code, no_group.json()['error']) == (404, 'group_not_found')

    # A deleted queue takes its rights along.
    await grant(first, support, ['view'])
    assert (await ada.delete(f'{base}/queues/{support["id"]}')).status_code == 204
    assert (await ada.get(f'{base}/queue-rights')).json()['grants'] == []


async def test_only_managers_of_queues_change_them(app: AppUnderTest) -> None:
    ada, tenant, base = await organization(app)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'manager')
    admin = await member_of(app, tenant, ada, 'cy@example.org', 'admin')
    queue = await created(ada, f'{base}/queues', name='Support')

    for method, path, body in (
        ('POST', f'{base}/queues', {'name': 'Mine'}),
        ('PATCH', f'{base}/queues/{queue["id"]}', {'name': 'Mine'}),
        ('DELETE', f'{base}/queues/{queue["id"]}', None),
        ('GET', f'{base}/groups', None),
        ('POST', f'{base}/groups', {'name': 'Mine'}),
        ('GET', f'{base}/queue-rights', None),
    ):
        response = await bob.request(method, path, json=body)
        assert (response.status_code, response.json()['params']) == (403, {'permission': 'queues.manage'}), path
    assert (await bob.get(f'{base}/queues')).json() == []

    # Admins manage queues and see all of them, but not with every right: that is queues.all (owners).
    listed = (await admin.get(f'{base}/queues')).json()
    assert [(each['name'], each['rights']) for each in listed] == [('Support', [])]
    assert (await admin.post(f'{base}/groups', json={'name': 'Admins'})).status_code == 201


async def test_api_keys_can_manage_queues(app: AppUnderTest) -> None:
    ada, _tenant, base = await organization(app)
    created_key = await ada.post(f'{base}/api-keys', json={'name': 'Provisioning', 'permissions': ['queues.manage']})
    assert created_key.status_code == 201, created_key.text
    key = app.new_client()
    key.headers['Authorization'] = f'Bearer {created_key.json()["key"]}'

    assert (await key.post(f'{base}/queues', json={'name': 'From the API'})).status_code == 201
    assert [each['name'] for each in (await key.get(f'{base}/queues')).json()] == ['From the API']


async def test_queue_access_answers_other_modules(app: AppUnderTest) -> None:
    ada, tenant, base = await organization(app)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    bob_id = await user_id_of(bob)
    queue = await created(ada, f'{base}/queues', name='Support')
    hidden = await created(ada, f'{base}/queues', name='Hidden')
    group = await created(ada, f'{base}/groups', name='Team')
    await ada.put(f'{base}/groups/{group["id"]}/members', json={'user_ids': [bob_id]})
    await ada.put(f'{base}/queue-rights', json={'group_id': group['id'], 'queue_id': queue['id'], 'rights': ['view']})
    await ada.put(f'{base}/queue-rights', json={'group_id': group['id'], 'queue_id': hidden['id'], 'rights': ['note']})

    access = app.app.context.contracts.queue_access.get()

    assert await access.rights(tenant, bob_id, queue['id']) == frozenset({'view'})
    assert await access.rights(tenant, bob_id, 'nowhere') == frozenset()
    assert await access.visible(tenant, bob_id) == {queue['id']: frozenset({'view'})}
    everything = await access.visible(tenant, bob_id, all_queues=True)
    assert set(everything) == {queue['id'], hidden['id']}
    assert everything[hidden['id']] == frozenset(FULL)


async def test_a_deleted_organization_takes_its_queues_and_groups(app: AppUnderTest) -> None:
    ada, _tenant, base = await organization(app)
    await created(ada, f'{base}/queues', name='Support')
    group = await created(ada, f'{base}/groups', name='Team')
    await ada.put(f'{base}/groups/{group["id"]}/members', json={'user_ids': [await user_id_of(ada)]})

    assert (await ada.delete(base)).status_code == 204

    async with app.app.db.connection() as connection:
        counts = await (
            await connection.execute(
                'SELECT (SELECT count(*) FROM queues) AS queues, (SELECT count(*) FROM groups) AS groups,'
                ' (SELECT count(*) FROM group_members) AS members'
            )
        ).fetchone()
    assert counts == {'queues': 0, 'groups': 0, 'members': 0}


async def test_a_deleted_account_leaves_every_group(app: AppUnderTest) -> None:
    ada, tenant, base = await organization(app)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    group = await created(ada, f'{base}/groups', name='Team')
    await ada.put(f'{base}/groups/{group["id"]}/members', json={'user_ids': [await user_id_of(bob)]})

    deleted = await bob.post('/api/v1/account/delete', json={'password': 'correct horse battery'})
    assert deleted.status_code == 204, deleted.text

    assert (await ada.get(f'{base}/groups')).json()[0]['member_ids'] == []


async def test_limits_queues_and_groups(app: AppUnderTest, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('zendilohub.modules.access.application.commands.queues.QUEUES_MAX', 1)
    monkeypatch.setattr('zendilohub.modules.access.application.commands.groups.GROUPS_MAX', 1)
    ada, _tenant, base = await organization(app)
    await created(ada, f'{base}/queues', name='One')
    await created(ada, f'{base}/groups', name='One')

    queue = await ada.post(f'{base}/queues', json={'name': 'Two'})
    group = await ada.post(f'{base}/groups', json={'name': 'Two'})

    assert (queue.status_code, queue.json()['error'], queue.json()['params']) == (409, 'queue_limit', {'limit': 1})
    assert (group.status_code, group.json()['error']) == (409, 'group_limit')
