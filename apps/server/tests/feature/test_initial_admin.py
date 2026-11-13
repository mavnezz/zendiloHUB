from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from support.app import AppUnderTest, fast_providers, running_app
from support.identity import PASSWORD, logged_in, make_admin
from support.services import Services
from zendilohub.core.application import Application
from zendilohub.core.config import InitialAdmin
from zendilohub.modules.identity.domain.exceptions import InvalidEmailError, WeakPasswordError

LOGIN = '/api/v1/auth/login'
USERS = '/api/v1/admin/users'
ADMIN = InitialAdmin(email='Admin@Example.org', password='first password')


async def restart(app: AppUnderTest, **overrides: Any) -> None:
    """Starts the app once more on the same database, e.g. with a changed environment."""
    again = Application.create(replace(app.config, **overrides), modules=fast_providers())
    try:
        await again.start(schedule=False)
    finally:
        await again.shutdown()


async def log_in(app: AppUnderTest, email: str, password: str) -> httpx.Response:
    return await app.new_client().post(LOGIN, json={'email': email, 'password': password})


async def test_creates_the_administrator_on_the_first_start(
    services: Services, template_database: None, tmp_path: Path
) -> None:
    async with running_app(services, tmp_path, 'test_initial_admin', initial_admin=ADMIN) as app:
        client = app.new_client()
        response = await client.post(LOGIN, json={'email': 'admin@example.org', 'password': 'first password'})
        assert response.status_code == 200, response.text
        assert response.json()['user']['role'] == 'admin'
        assert (await client.get(USERS)).json()['total'] == 1

        # Started again with another password: the administrator exists, nothing changes.
        await restart(app, initial_admin=InitialAdmin(email='admin@example.org', password='second password'))
        assert (await log_in(app, 'admin@example.org', 'first password')).status_code == 200
        assert (await log_in(app, 'admin@example.org', 'second password')).status_code == 401
        assert (await client.get(USERS)).json()['total'] == 1


async def test_creates_none_while_there_is_an_administrator(app: AppUnderTest) -> None:
    grace = await logged_in(app, 'grace@example.org')
    await make_admin(app, 'grace@example.org')

    await restart(app, initial_admin=ADMIN)

    assert (await log_in(app, 'admin@example.org', 'first password')).status_code == 401
    assert (await grace.get(USERS)).json()['total'] == 1


async def test_an_existing_account_becomes_the_administrator_with_its_own_password(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    assert (await ada.get(USERS)).status_code == 403

    await restart(app, initial_admin=InitialAdmin(email=' ADA@example.org', password='another password'))

    assert (await ada.get(USERS)).status_code == 200
    assert (await log_in(app, 'ada@example.org', PASSWORD)).status_code == 200
    assert (await log_in(app, 'ada@example.org', 'another password')).status_code == 401


@pytest.mark.parametrize(
    ('admin', 'error'),
    [
        (InitialAdmin(email='admin@example.org', password='short'), WeakPasswordError),
        (InitialAdmin(email='not an address', password='first password'), InvalidEmailError),
    ],
)
async def test_refuses_to_start_with_an_invalid_administrator(
    app: AppUnderTest, admin: InitialAdmin, error: type[Exception]
) -> None:
    with pytest.raises(error):
        await restart(app, initial_admin=admin)


async def test_only_the_app_creates_the_administrator(app: AppUnderTest) -> None:
    cli = Application.create(replace(app.config, initial_admin=ADMIN), modules=fast_providers(), role='cli')
    try:
        await cli.start(schedule=False)
    finally:
        await cli.shutdown()

    assert (await log_in(app, 'admin@example.org', 'first password')).status_code == 401
