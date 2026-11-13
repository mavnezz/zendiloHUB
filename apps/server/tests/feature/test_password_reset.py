from support.app import AppUnderTest
from support.identity import PASSWORD, logged_in

FORGOT = '/api/v1/auth/forgot-password'
RESET = '/api/v1/auth/reset-password'
LOGIN = '/api/v1/auth/login'


async def test_resets_the_password_and_logs_out_everywhere(app: AppUnderTest) -> None:
    other_device = await logged_in(app, 'ada@example.org')

    assert (await app.client.post(FORGOT, json={'email': 'Ada@Example.org'})).status_code == 204
    mail = app.mailer.to('ada@example.org')[-1]
    assert mail.subject == 'Reset your zendiloHUB password'
    assert app.mailer.last_link('ada@example.org').startswith('http://zendilohub.test/reset-password?token=')

    response = await app.client.post(
        RESET, json={'token': app.mailer.last_token('ada@example.org'), 'password': 'a new password'}
    )
    assert response.status_code == 200
    assert response.json()['user']['email'] == 'ada@example.org'
    assert (await app.client.get('/api/v1/account')).status_code == 200
    assert (await other_device.get('/api/v1/account')).status_code == 401

    assert (
        await app.new_client().post(LOGIN, json={'email': 'ada@example.org', 'password': PASSWORD})
    ).status_code == 401
    response = await app.new_client().post(LOGIN, json={'email': 'ada@example.org', 'password': 'a new password'})
    assert response.status_code == 200


async def test_answers_the_same_for_unknown_addresses(app: AppUnderTest) -> None:
    assert (await app.client.post(FORGOT, json={'email': 'nobody@example.org'})).status_code == 204
    assert (await app.client.post(FORGOT, json={'email': 'not an address'})).status_code == 204
    assert app.mailer.sent == []


async def test_links_work_once_and_only_the_newest_one(app: AppUnderTest) -> None:
    await logged_in(app, 'ada@example.org')
    await app.client.post(FORGOT, json={'email': 'ada@example.org'})
    first = app.mailer.last_token('ada@example.org')
    await app.client.post(FORGOT, json={'email': 'ada@example.org'})
    second = app.mailer.last_token('ada@example.org')

    response = await app.client.post(RESET, json={'token': first, 'password': 'a new password'})
    assert response.json()['error'] == 'invalid_token'
    assert (await app.client.post(RESET, json={'token': second, 'password': 'a new password'})).status_code == 200
    assert (await app.client.post(RESET, json={'token': second, 'password': 'another one!!'})).status_code == 422


async def test_links_expire_after_an_hour(app: AppUnderTest) -> None:
    await logged_in(app, 'ada@example.org')
    await app.client.post(FORGOT, json={'email': 'ada@example.org'})
    app.clock.advance(hours=1)
    response = await app.client.post(
        RESET, json={'token': app.mailer.last_token('ada@example.org'), 'password': 'a new password'}
    )
    assert response.status_code == 422
    assert response.json()['error'] == 'invalid_token'


async def test_the_new_password_must_be_good_enough(app: AppUnderTest) -> None:
    await logged_in(app, 'ada@example.org')
    await app.client.post(FORGOT, json={'email': 'ada@example.org'})
    response = await app.client.post(
        RESET, json={'token': app.mailer.last_token('ada@example.org'), 'password': 'short'}
    )
    assert response.status_code == 422
    assert response.json()['error'] == 'weak_password'


async def test_e_mails_are_in_the_users_language(app: AppUnderTest) -> None:
    client = await logged_in(app, 'ada@example.org')
    response = await client.patch('/api/v1/account', json={'locale': 'de'})
    assert response.json()['locale'] == 'de'

    await app.client.post(FORGOT, json={'email': 'ada@example.org'})
    assert app.mailer.to('ada@example.org')[-1].subject == 'Setze dein zendiloHUB-Passwort zurück'
