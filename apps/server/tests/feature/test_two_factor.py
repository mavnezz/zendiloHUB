import httpx

from support.app import AppUnderTest
from support.identity import PASSWORD, logged_in, make_admin
from zendilohub.modules.identity.domain.models import totp

LOGIN = '/api/v1/auth/login'
SECOND_STEP = '/api/v1/auth/login/two-factor'
TWO_FACTOR = '/api/v1/account/two-factor'


def code(app: AppUnderTest, secret: str, *, steps: int = 0) -> str:
    return totp.code_at(secret, totp.step_at(app.clock.now()) + steps)


async def enable(app: AppUnderTest, client: httpx.AsyncClient) -> tuple[str, list[str]]:
    """Turns two-factor login on; returns the secret and the recovery codes."""
    response = await client.post(f'{TWO_FACTOR}/setup', json={'password': PASSWORD})
    assert response.status_code == 200, response.text
    secret = response.json()['secret']
    response = await client.post(f'{TWO_FACTOR}/enable', json={'code': code(app, secret)})
    assert response.status_code == 200, response.text
    # The code just used is spent: the next login needs a later one.
    app.clock.advance(seconds=30)
    return secret, response.json()['recovery_codes']


async def challenge(app: AppUnderTest, client: httpx.AsyncClient | None = None) -> str:
    response = await (client or app.new_client()).post(LOGIN, json={'email': 'ada@example.org', 'password': PASSWORD})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['user'] is None
    assert 'set-cookie' not in response.headers
    return str(body['challenge'])


async def test_sets_up_two_factor_login_and_asks_for_the_code(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    other_device = app.new_client()
    await other_device.post(LOGIN, json={'email': 'ada@example.org', 'password': PASSWORD})
    assert (await ada.get(TWO_FACTOR)).json() == {'enabled': False, 'recovery_codes_left': 0}

    assert (await ada.post(f'{TWO_FACTOR}/setup', json={'password': 'wrong'})).json()['error'] == (
        'invalid_current_password'
    )
    assert (await ada.post(f'{TWO_FACTOR}/enable', json={'code': '123456'})).json()['error'] == (
        'two_factor_not_started'
    )
    setup = (await ada.post(f'{TWO_FACTOR}/setup', json={'password': PASSWORD})).json()
    assert setup['uri'] == (
        f'otpauth://totp/zendiloHUB:ada@example.org?secret={setup["secret"]}&issuer=zendiloHUB'
        '&algorithm=SHA1&digits=6&period=30'
    )
    # Not on before a code confirms the app has the secret.
    assert (await ada.get(TWO_FACTOR)).json()['enabled'] is False
    assert (await ada.post(f'{TWO_FACTOR}/enable', json={'code': '000000'})).json()['error'] == (
        'invalid_two_factor_code'
    )
    response = await ada.post(f'{TWO_FACTOR}/enable', json={'code': code(app, setup['secret'])})
    codes = response.json()['recovery_codes']
    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert (await ada.get(TWO_FACTOR)).json() == {'enabled': True, 'recovery_codes_left': 10}
    assert (await ada.get('/api/v1/account')).json()['two_factor'] is True
    # Other sessions end; this one stays.
    assert (await other_device.get('/api/v1/account')).status_code == 401
    assert (await ada.post(f'{TWO_FACTOR}/setup', json={'password': PASSWORD})).json()['error'] == 'two_factor_on'

    app.clock.advance(seconds=30)
    client = app.new_client()
    token = await challenge(app, client)
    assert (await client.get('/api/v1/account')).status_code == 401
    response = await client.post(SECOND_STEP, json={'challenge': token, 'code': code(app, setup['secret'])})
    assert response.status_code == 200
    assert response.json()['user']['email'] == 'ada@example.org'
    assert (await client.get('/api/v1/account')).status_code == 200
    # The challenge is used up.
    response = await client.post(SECOND_STEP, json={'challenge': token, 'code': code(app, setup['secret'], steps=1)})
    assert response.json()['error'] == 'invalid_challenge'


async def test_a_code_works_only_once_and_in_its_time(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    secret, _ = await enable(app, ada)

    first = code(app, secret)
    assert (
        await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': first})
    ).status_code == (200)
    response = await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': first})
    assert response.json()['error'] == 'invalid_two_factor_code'
    # The neighboring steps count (clock drift), older ones not.
    later = code(app, secret, steps=1)
    assert (
        await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': later})
    ).status_code == (200)
    app.clock.advance(minutes=5)
    old = code(app, secret, steps=-3)
    response = await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': old})
    assert response.json()['error'] == 'invalid_two_factor_code'


async def test_recovery_codes_work_once(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    _, codes = await enable(app, ada)

    typed = ' ' + codes[0].upper().replace('-', ' - ') + ' '
    response = await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': typed})
    assert response.status_code == 200
    assert (await ada.get(TWO_FACTOR)).json()['recovery_codes_left'] == 9
    response = await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': codes[0]})
    assert response.json()['error'] == 'invalid_two_factor_code'

    # New codes replace the old ones.
    assert (await ada.post(f'{TWO_FACTOR}/recovery-codes', json={'password': 'wrong'})).status_code == 422
    fresh = (await ada.post(f'{TWO_FACTOR}/recovery-codes', json={'password': PASSWORD})).json()['recovery_codes']
    assert (await ada.get(TWO_FACTOR)).json()['recovery_codes_left'] == 10
    response = await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': codes[1]})
    assert response.json()['error'] == 'invalid_two_factor_code'
    assert (
        await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': fresh[0]})
    ).status_code == 200


async def test_a_challenge_allows_five_attempts_and_five_minutes(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    secret, _ = await enable(app, ada)

    token = await challenge(app)
    for _ in range(4):
        response = await app.client.post(SECOND_STEP, json={'challenge': token, 'code': '000000'})
        assert response.json()['error'] == 'invalid_two_factor_code'
    response = await app.client.post(SECOND_STEP, json={'challenge': token, 'code': 'not a code'})
    assert response.json()['error'] == 'invalid_two_factor_code'
    response = await app.client.post(SECOND_STEP, json={'challenge': token, 'code': code(app, secret)})
    assert response.json()['error'] == 'invalid_challenge'

    token = await challenge(app)
    app.clock.advance(minutes=5)
    response = await app.client.post(SECOND_STEP, json={'challenge': token, 'code': code(app, secret)})
    assert response.json()['error'] == 'invalid_challenge'
    response = await app.client.post(SECOND_STEP, json={'challenge': 'made up', 'code': code(app, secret)})
    assert response.json()['error'] == 'invalid_challenge'


async def test_limits_wrong_codes_per_account(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    secret, _ = await enable(app, ada)
    for _ in range(2):
        token = await challenge(app)
        for _ in range(5):
            await app.client.post(SECOND_STEP, json={'challenge': token, 'code': '000000'})

    response = await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': code(app, secret)})
    assert response.status_code == 429
    app.clock.advance(minutes=15)
    response = await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': code(app, secret)})
    assert response.status_code == 200


async def test_turns_two_factor_login_off(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    secret, _ = await enable(app, ada)
    token = await challenge(app)

    assert (await ada.post(f'{TWO_FACTOR}/disable', json={'password': 'wrong'})).status_code == 422
    assert (await ada.post(f'{TWO_FACTOR}/disable', json={'password': PASSWORD})).status_code == 204
    assert (await ada.get(TWO_FACTOR)).json() == {'enabled': False, 'recovery_codes_left': 0}
    assert (await ada.post(f'{TWO_FACTOR}/disable', json={'password': PASSWORD})).json()['error'] == 'two_factor_off'
    assert (await ada.post(f'{TWO_FACTOR}/recovery-codes', json={'password': PASSWORD})).json()['error'] == (
        'two_factor_off'
    )
    # A challenge from before does not finish the login any more; the password alone does now.
    response = await app.client.post(SECOND_STEP, json={'challenge': token, 'code': code(app, secret)})
    assert response.json()['error'] == 'invalid_challenge'
    response = await app.new_client().post(LOGIN, json={'email': 'ada@example.org', 'password': PASSWORD})
    assert response.json()['user']['two_factor'] is False


async def test_an_administrator_resets_a_lost_device(app: AppUnderTest) -> None:
    grace = await logged_in(app, 'grace@example.org')
    await make_admin(app, 'grace@example.org')
    ada = await logged_in(app, 'ada@example.org')
    await enable(app, ada)
    users = (await grace.get('/api/v1/admin/users', params={'q': 'ada'})).json()['items']
    assert users[0]['two_factor'] is True
    ada_id = users[0]['id']
    grace_id = (await grace.get('/api/v1/account')).json()['id']

    assert (await ada.delete(f'/api/v1/admin/users/{grace_id}/two-factor')).status_code == 403
    assert (await grace.delete(f'/api/v1/admin/users/{grace_id}/two-factor')).json()['error'] == 'own_account'
    assert (await grace.delete(f'/api/v1/admin/users/{ada_id}/two-factor')).status_code == 204
    assert (await grace.delete(f'/api/v1/admin/users/{ada_id}/two-factor')).json()['error'] == 'two_factor_off'
    missing = '00000000-0000-4000-8000-000000000000'
    assert (await grace.delete(f'/api/v1/admin/users/{missing}/two-factor')).status_code == 404
    # Ada is logged out everywhere and logs in with the password alone.
    assert (await ada.get('/api/v1/account')).status_code == 401
    response = await app.new_client().post(LOGIN, json={'email': 'ada@example.org', 'password': PASSWORD})
    assert response.json()['user']['email'] == 'ada@example.org'


async def test_a_password_reset_still_asks_for_the_code(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    secret, _ = await enable(app, ada)

    await app.client.post('/api/v1/auth/forgot-password', json={'email': 'ada@example.org'})
    client = app.new_client()
    response = await client.post(
        '/api/v1/auth/reset-password',
        json={'token': app.mailer.last_token('ada@example.org'), 'password': 'a new password'},
    )
    assert response.status_code == 200
    assert response.json()['user'] is None
    assert (await client.get('/api/v1/account')).status_code == 401
    response = await client.post(
        SECOND_STEP, json={'challenge': response.json()['challenge'], 'code': code(app, secret)}
    )
    assert response.status_code == 200
    assert (await client.get('/api/v1/account')).status_code == 200


async def test_the_audit_log_records_two_factor_logins(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    secret, _ = await enable(app, ada)
    await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': code(app, secret)})
    await app.client.post(SECOND_STEP, json={'challenge': await challenge(app), 'code': '000000'})
    root = await logged_in(app, 'root@example.org')
    await make_admin(app, 'root@example.org')

    page = (await root.get('/api/v1/admin/audit-log')).json()

    actions = [(entry['action'], entry['actor_email'], entry['succeeded']) for entry in page['items']]
    assert ('account.two_factor_setup_started', 'ada@example.org', True) in actions
    assert ('account.two_factor_enabled', 'ada@example.org', True) in actions
    assert ('auth.login_two_factor', 'ada@example.org', True) in actions
    assert ('auth.login_two_factor', None, False) in actions
