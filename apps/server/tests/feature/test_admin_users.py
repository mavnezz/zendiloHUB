from support.app import AppUnderTest
from support.fakes import MemoryOutput
from support.identity import logged_in, make_admin

USERS = '/api/v1/admin/users'


async def test_only_administrators_manage_users(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    assert (await ada.get(USERS)).status_code == 403
    assert (await app.new_client().get(USERS)).status_code == 401


async def test_lists_and_searches_users(app: AppUnderTest) -> None:
    grace = await logged_in(app, 'grace@example.org')
    await make_admin(app, 'grace@example.org')
    for name in ('ada', 'alan', 'barbara'):
        await logged_in(app, f'{name}@example.org')
        app.clock.advance(minutes=1)

    page = (await grace.get(USERS)).json()
    assert page['total'] == 4
    assert [user['email'] for user in page['items']] == [
        'barbara@example.org',
        'alan@example.org',
        'ada@example.org',
        'grace@example.org',
    ]
    page = (await grace.get(USERS, params={'q': ' BAR '})).json()
    assert [user['email'] for user in page['items']] == ['barbara@example.org']
    page = (await grace.get(USERS, params={'q': 'example', 'limit': 1, 'offset': 1})).json()
    assert page['total'] == 4
    assert [user['email'] for user in page['items']] == ['alan@example.org']
    assert (await grace.get(USERS, params={'q': '%'})).json()['total'] == 0
    everyone = (await grace.get(USERS)).json()['items']
    ada_id, alan_id = everyone[2]['id'], everyone[1]['id']
    picked = (await grace.get(USERS, params=[('ids', ada_id), ('ids', alan_id)])).json()
    assert [user['email'] for user in picked['items']] == ['alan@example.org', 'ada@example.org']
    assert (await grace.get(USERS, params={'limit': 0})).status_code == 422


async def test_changes_roles_and_deletes_users(app: AppUnderTest) -> None:
    grace = await logged_in(app, 'grace@example.org')
    await make_admin(app, 'grace@example.org')
    ada = await logged_in(app, 'ada@example.org')
    ada_id = (await ada.get('/api/v1/account')).json()['id']
    grace_id = (await grace.get('/api/v1/account')).json()['id']

    response = await grace.patch(f'{USERS}/{ada_id}', json={'role': 'admin'})
    assert response.json()['role'] == 'admin'
    assert (await ada.get(USERS)).status_code == 200
    assert (await grace.patch(f'{USERS}/{ada_id}', json={'role': 'user'})).json()['role'] == 'user'
    assert (await ada.get(USERS)).status_code == 403

    response = await grace.patch(f'{USERS}/{grace_id}', json={'role': 'user'})
    assert response.status_code == 409
    assert response.json()['error'] == 'own_account'
    assert (await grace.delete(f'{USERS}/{grace_id}')).json()['error'] == 'own_account'
    assert (
        await grace.patch(f'{USERS}/00000000-0000-7000-8000-999999999999', json={'role': 'user'})
    ).status_code == 404
    assert (await grace.patch(f'{USERS}/{ada_id}', json={'role': 'owner'})).status_code == 422

    assert (await grace.delete(f'{USERS}/{ada_id}')).status_code == 204
    assert (await ada.get('/api/v1/account')).status_code == 401
    assert (await grace.delete(f'{USERS}/{ada_id}')).status_code == 404


async def test_an_administrator_cannot_be_demoted_if_they_are_the_last_one(app: AppUnderTest) -> None:
    """Only reachable through a race (the actor is an admin, too), so it is checked on the handler directly."""
    from zendilohub.modules.identity.domain.exceptions import LastAdminError

    await logged_in(app, 'grace@example.org')
    await make_admin(app, 'grace@example.org')
    async with app.app.db.connection() as connection:
        row = await (await connection.execute("SELECT id FROM users WHERE email = 'grace@example.org'")).fetchone()
    assert row is not None
    from zendilohub.modules.identity.application.commands.change_role import ChangeRole, ChangeRoleHandler
    from zendilohub.modules.identity.infrastructure.postgres_users import PostgresUserRepository

    handler = ChangeRoleHandler(PostgresUserRepository(app.app.db), app.clock)
    try:
        await handler.handle(ChangeRole(actor_id='someone-else', user_id=str(row['id']), role='user'))
    except LastAdminError:
        pass
    else:
        raise AssertionError('expected LastAdminError')


async def test_make_admin_cli(app: AppUnderTest) -> None:
    await logged_in(app, 'grace@example.org')
    output = MemoryOutput()
    assert await app.app.run_command(['make-admin', 'Grace@Example.org'], output) == 0
    assert output.lines == ['grace@example.org is an administrator now.']

    output = MemoryOutput()
    assert await app.app.run_command(['make-admin', 'nobody@example.org'], output) == 1
    assert output.errors == ['The user does not exist']
    output = MemoryOutput()
    assert await app.app.run_command(['make-admin'], output) == 1
    assert output.errors == ['Usage: zendilohub make-admin <email>']


async def test_rejects_invalid_user_ids(app: AppUnderTest) -> None:
    grace = await logged_in(app, 'grace@example.org')
    await make_admin(app, 'grace@example.org')
    assert (await grace.delete(f'{USERS}/42')).status_code == 422
    assert (await grace.get(USERS, params={'ids': 'nope'})).status_code == 422
