from support.app import AppUnderTest
from support.identity import PASSWORD, logged_in

LOGIN = '/api/v1/auth/login'
SESSION = '/api/v1/auth/session'


async def test_logs_in_and_out(app: AppUnderTest) -> None:
    await logged_in(app, 'ada@example.org')

    response = await app.client.post(LOGIN, json={'email': 'ADA@example.org', 'password': PASSWORD})
    assert response.status_code == 200
    assert response.json()['user']['email'] == 'ada@example.org'
    assert (await app.client.get(SESSION)).json()['user']['email'] == 'ada@example.org'
    assert (await app.client.get('/api/v1/account')).status_code == 200

    response = await app.client.post('/api/v1/auth/logout')
    assert response.status_code == 204
    assert 'zendilohub_session=""' in response.headers['set-cookie']
    assert (await app.client.get(SESSION)).json() == {'user': None, 'challenge': None}
    assert (await app.client.get('/api/v1/account')).status_code == 401
    # Logging out without a session is fine, too.
    assert (await app.new_client().post('/api/v1/auth/logout')).status_code == 204


async def test_a_logged_out_token_stays_invalid(app: AppUnderTest) -> None:
    client = await logged_in(app, 'ada@example.org')
    token = client.cookies['zendilohub_session']
    await client.post('/api/v1/auth/logout')

    stolen = app.new_client()
    stolen.cookies['zendilohub_session'] = token
    assert (await stolen.get(SESSION)).json() == {'user': None, 'challenge': None}


async def test_rejects_wrong_credentials_the_same_way(app: AppUnderTest) -> None:
    await logged_in(app, 'ada@example.org')
    for body in (
        {'email': 'ada@example.org', 'password': 'wrong password'},
        {'email': 'nobody@example.org', 'password': PASSWORD},
        {'email': 'not an address', 'password': PASSWORD},
    ):
        response = await app.client.post(LOGIN, json=body)
        assert response.status_code == 401
        assert response.json() == {'error': 'invalid_credentials', 'message': 'E-mail address or password is wrong'}


async def test_locks_an_address_after_too_many_failures(app: AppUnderTest) -> None:
    await logged_in(app, 'ada@example.org')
    for _ in range(10):
        await app.client.post(LOGIN, json={'email': 'ada@example.org', 'password': 'wrong password'})

    response = await app.client.post(LOGIN, json={'email': 'ada@example.org', 'password': PASSWORD})
    assert response.status_code == 429
    assert response.json()['error'] == 'too_many_requests'
    assert response.json()['params']['minutes'] == 15

    app.clock.advance(minutes=15)
    assert (await app.client.post(LOGIN, json={'email': 'ada@example.org', 'password': PASSWORD})).status_code == 200


async def test_a_successful_login_forgives_earlier_failures(app: AppUnderTest) -> None:
    await logged_in(app, 'ada@example.org')
    for _ in range(9):
        await app.client.post(LOGIN, json={'email': 'ada@example.org', 'password': 'wrong password'})
    assert (await app.client.post(LOGIN, json={'email': 'ada@example.org', 'password': PASSWORD})).status_code == 200
    for _ in range(9):
        await app.client.post(LOGIN, json={'email': 'ada@example.org', 'password': 'wrong password'})
    assert (await app.client.post(LOGIN, json={'email': 'ada@example.org', 'password': PASSWORD})).status_code == 200


async def test_sessions_expire_after_30_days(app: AppUnderTest) -> None:
    client = await logged_in(app, 'ada@example.org')
    app.clock.advance(days=30)
    assert (await client.get(SESSION)).json() == {'user': None, 'challenge': None}
    assert (await client.get('/api/v1/account')).status_code == 401


async def test_upgrades_password_hashes_made_with_old_parameters(app: AppUnderTest) -> None:
    await logged_in(app, 'ada@example.org')
    async with app.app.db.connection() as connection:
        # A hash with other (here: even weaker) parameters, as if the defaults had changed since.
        import argon2

        old = argon2.PasswordHasher(time_cost=1, memory_cost=16, parallelism=2).hash(PASSWORD)
        await connection.execute('UPDATE users SET password_hash = %s', (old,))

    assert (await app.client.post(LOGIN, json={'email': 'ada@example.org', 'password': PASSWORD})).status_code == 200
    async with app.app.db.connection() as connection:
        row = await (await connection.execute('SELECT password_hash FROM users')).fetchone()
    assert row is not None
    assert row['password_hash'] != old
    assert 'p=1' in row['password_hash']
