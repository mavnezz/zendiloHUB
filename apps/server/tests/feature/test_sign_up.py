from pathlib import Path

import pytest

from support.app import AppUnderTest, running_app
from support.identity import PASSWORD, sign_up
from support.services import Services
from zendilohub.core.events.integration_events import UserRegistered

REGISTER = '/api/v1/auth/register'
CONFIRM = '/api/v1/auth/confirm'


async def test_signing_up_sends_a_link_that_creates_the_account_and_logs_in(app: AppUnderTest) -> None:
    registered: list[UserRegistered] = []

    async def remember(event: UserRegistered) -> None:
        registered.append(event)

    app.app.context.events.subscribe(UserRegistered, remember)
    response = await app.client.post(
        REGISTER, json={'email': ' Ada@Example.org ', 'password': PASSWORD, 'locale': 'de'}
    )
    assert response.status_code == 204

    [mail] = app.mailer.to('ada@example.org')
    assert mail.subject == 'Bestätige dein zendiloHUB-Konto'
    assert app.mailer.last_link('ada@example.org').startswith('http://zendilohub.test/verify-email?token=')
    # Nothing exists before the confirmation.
    assert (await app.client.get('/api/v1/auth/session')).json() == {'user': None, 'challenge': None}

    response = await app.client.post(CONFIRM, json={'token': app.mailer.last_token('ada@example.org')})
    assert response.status_code == 200
    user = response.json()['user']
    assert user['email'] == 'ada@example.org'
    assert user['role'] == 'user'
    assert user['locale'] == 'de'
    cookie = response.headers['set-cookie']
    assert 'zendilohub_session=' in cookie
    assert 'HttpOnly' in cookie
    assert 'SameSite=lax' in cookie
    assert (await app.client.get('/api/v1/auth/session')).json()['user']['id'] == user['id']
    assert registered == [UserRegistered(user_id=user['id'], email='ada@example.org')]


@pytest.mark.usefixtures('template_database')
async def test_links_in_e_mails_use_the_public_url(services: Services, tmp_path: Path) -> None:
    async with running_app(services, tmp_path, 'test_public_url', public_url='https://print.example.org') as app:
        await sign_up(app, 'ada@example.org')
        assert app.mailer.last_link('ada@example.org').startswith('https://print.example.org/verify-email?token=')


async def test_a_link_works_only_once(app: AppUnderTest) -> None:
    token = await sign_up(app, 'ada@example.org')
    assert (await app.client.post(CONFIRM, json={'token': token})).status_code == 200

    response = await app.new_client().post(CONFIRM, json={'token': token})
    assert response.status_code == 422
    assert response.json()['error'] == 'invalid_token'


async def test_a_link_expires_after_48_hours(app: AppUnderTest) -> None:
    token = await sign_up(app, 'ada@example.org')
    app.clock.advance(hours=48)
    response = await app.client.post(CONFIRM, json={'token': token})
    assert response.status_code == 422
    assert response.json()['error'] == 'invalid_token'


async def test_an_existing_account_gets_a_hint_instead_and_the_answer_is_the_same(app: AppUnderTest) -> None:
    token = await sign_up(app, 'ada@example.org')
    await app.client.post(CONFIRM, json={'token': token})

    response = await app.new_client().post(REGISTER, json={'email': 'ada@example.org', 'password': 'other password!'})
    assert response.status_code == 204
    mail = app.mailer.to('ada@example.org')[-1]
    assert mail.subject == 'Your zendiloHUB account'
    assert 'http://zendilohub.test/login' in mail.text
    # The old password still works; the attempt changed nothing.
    response = await app.new_client().post(
        '/api/v1/auth/login', json={'email': 'ada@example.org', 'password': PASSWORD}
    )
    assert response.status_code == 200


async def test_only_the_confirmed_sign_up_decides_the_password(app: AppUnderTest) -> None:
    """Someone signing up with another person's address must not end up knowing their password."""
    mallory = await sign_up(app, 'ada@example.org', 'mallory password')
    ada = await sign_up(app, 'ada@example.org', 'ada password!!')

    assert (await app.new_client().post(CONFIRM, json={'token': ada})).status_code == 200
    assert (await app.new_client().post(CONFIRM, json={'token': mallory})).json()['error'] == 'invalid_token'

    login = '/api/v1/auth/login'
    assert (
        await app.new_client().post(login, json={'email': 'ada@example.org', 'password': 'ada password!!'})
    ).is_success
    response = await app.new_client().post(login, json={'email': 'ada@example.org', 'password': 'mallory password'})
    assert response.status_code == 401


async def test_validates_the_address_and_the_password(app: AppUnderTest) -> None:
    response = await app.client.post(REGISTER, json={'email': 'not an address', 'password': PASSWORD})
    assert response.status_code == 422
    assert response.json()['error'] == 'invalid_email'

    response = await app.client.post(REGISTER, json={'email': 'ada@example.org', 'password': 'short'})
    assert response.status_code == 422
    assert response.json() == {
        'error': 'weak_password',
        'message': 'The password must have between 10 and 128 characters',
        'params': {'min_length': 10, 'max_length': 128},
    }

    response = await app.client.post(REGISTER, json={'email': 'ada@example.org', 'password': PASSWORD, 'role': 'admin'})
    assert response.status_code == 422
    assert response.json()['error'] == 'invalid_request'


async def test_logging_in_before_confirming_explains_what_to_do(app: AppUnderTest) -> None:
    await sign_up(app, 'ada@example.org')
    login = '/api/v1/auth/login'

    response = await app.client.post(login, json={'email': 'ada@example.org', 'password': PASSWORD})
    assert response.status_code == 403
    assert response.json()['error'] == 'email_not_verified'
    # Without the right password, nothing is revealed.
    response = await app.client.post(login, json={'email': 'ada@example.org', 'password': 'wrong password'})
    assert response.status_code == 401


async def test_resends_the_link_to_whoever_knows_the_password(app: AppUnderTest) -> None:
    first = await sign_up(app, 'ada@example.org')
    resend = '/api/v1/auth/resend-confirmation'

    assert (
        await app.client.post(resend, json={'email': 'ada@example.org', 'password': 'wrong password'})
    ).status_code == 204
    assert len(app.mailer.to('ada@example.org')) == 1
    assert (
        await app.client.post(resend, json={'email': 'nobody@example.org', 'password': PASSWORD})
    ).status_code == 204
    assert (await app.client.post(resend, json={'email': 'not an address', 'password': PASSWORD})).status_code == 204

    assert (await app.client.post(resend, json={'email': 'ada@example.org', 'password': PASSWORD})).status_code == 204
    second = app.mailer.last_token('ada@example.org')
    assert second != first
    assert (await app.client.post(CONFIRM, json={'token': first})).status_code == 422
    assert (await app.client.post(CONFIRM, json={'token': second})).status_code == 200


async def test_limits_the_e_mails_per_address(app: AppUnderTest) -> None:
    for _ in range(5):
        await sign_up(app, 'ada@example.org')
    response = await app.client.post(REGISTER, json={'email': 'ada@example.org', 'password': PASSWORD})
    assert response.status_code == 429
    assert response.json()['error'] == 'too_many_requests'
    assert int(response.headers['retry-after']) > 0
    assert len(app.mailer.to('ada@example.org')) == 5

    app.clock.advance(hours=1)
    assert (await app.client.post(REGISTER, json={'email': 'ada@example.org', 'password': PASSWORD})).status_code == 204


async def test_a_sign_up_for_an_address_that_got_an_account_meanwhile_is_dropped(app: AppUnderTest) -> None:
    """A race: both links were opened at the same moment; the second one must not fail with a server error."""
    from zendilohub.modules.identity.domain.models.registration import Registration
    from zendilohub.modules.identity.infrastructure.postgres_users import PostgresRegistrationRepository
    from zendilohub.modules.identity.infrastructure.security import Sha256TokenService

    await app.client.post(CONFIRM, json={'token': await sign_up(app, 'ada@example.org')})
    issued = Sha256TokenService().issue()
    registrations = PostgresRegistrationRepository(app.app.db)
    late = Registration.start(
        id=issued.id, email='ada@example.org', password_hash='x', locale='en', now=app.clock.now()
    )
    await registrations.save(late)

    response = await app.new_client().post(CONFIRM, json={'token': issued.token})
    assert response.json()['error'] == 'invalid_token'
    assert await registrations.find_by_email('ada@example.org') == []


async def test_a_login_does_not_tell_whether_an_address_has_an_account(app: AppUnderTest) -> None:
    """Sign up someone else's address, then log in with the chosen password: same answer either way."""
    await app.client.post(CONFIRM, json={'token': await sign_up(app, 'ada@example.org')})
    login = '/api/v1/auth/login'
    answers = []
    for email in ('ada@example.org', 'nobody@example.org'):
        await app.new_client().post(REGISTER, json={'email': email, 'password': 'mallory password'})
        response = await app.new_client().post(login, json={'email': email, 'password': 'mallory password'})
        answers.append((response.status_code, response.json()['error']))
    assert answers == [(403, 'email_not_verified'), (403, 'email_not_verified')]

    # Asking for the link again gives the owner of the account a hint, never a link for the other sign-up.
    resend = '/api/v1/auth/resend-confirmation'
    await app.new_client().post(resend, json={'email': 'ada@example.org', 'password': 'mallory password'})
    assert app.mailer.to('ada@example.org')[-1].subject == 'Your zendiloHUB account'
    assert all('verify-email' not in mail.text for mail in app.mailer.to('ada@example.org')[1:])
    # The owner still logs in with their password.
    response = await app.new_client().post(login, json={'email': 'ada@example.org', 'password': PASSWORD})
    assert response.status_code == 200
