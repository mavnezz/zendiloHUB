import logging
from pathlib import Path
from typing import Any

import pytest

from support.app import AppUnderTest, running_app
from support.identity import PASSWORD, logged_in
from support.services import Services
from support.tenancy import TENANTS, create_tenant
from zendilohub.core.config import InitialAdmin

SETUP = '/api/v1/setup'


def setup_code(app: AppUnderTest) -> str:
    return (app.config.data_dir / 'setup-token').read_text('utf-8').strip()


def wizard(app: AppUnderTest, **fields: Any) -> dict[str, Any]:
    return {
        'token': setup_code(app),
        'email': ' Ada@Example.org ',
        'password': PASSWORD,
        'organization_name': 'Acme GmbH',
        'timezone': 'Europe/Berlin',
        'locale': 'de',
        **fields,
    }


async def test_a_new_self_hosted_instance_opens_the_setup_wizard(self_hosted: AppUnderTest) -> None:
    assert (await self_hosted.client.get(SETUP)).json() == {'open': True, 'self_hosted': True}
    code = setup_code(self_hosted)
    assert len(code) == 20
    assert oct((self_hosted.config.data_dir / 'setup-token').stat().st_mode & 0o777) == '0o600'


async def test_tells_the_operator_the_setup_code(self_hosted: AppUnderTest, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    for module in self_hosted.app.modules:
        await module.boot()

    assert f'enter the setup code {setup_code(self_hosted)}' in caplog.text


async def test_the_wizard_makes_the_administrator_and_the_organization(self_hosted: AppUnderTest) -> None:
    client = self_hosted.new_client()

    body = wizard(self_hosted)
    response = await client.post(SETUP, json=body)

    assert response.status_code == 200, response.text
    user = response.json()['user']
    assert (user['email'], user['role'], user['locale']) == ('ada@example.org', 'admin', 'de')
    [own] = (await client.get(TENANTS)).json()
    assert (own['name'], own['role'], own['timezone'], own['locale']) == ('Acme GmbH', 'owner', 'Europe/Berlin', 'de')
    assert (await client.get(SETUP)).json() == {'open': False, 'self_hosted': True}
    assert not (self_hosted.config.data_dir / 'setup-token').exists()
    admin_log = (await client.get('/api/v1/admin/audit-log')).json()['items']
    assert ('setup.completed', 'ada@example.org', True) in [
        (entry['action'], entry['actor_email'], entry['succeeded']) for entry in admin_log
    ]

    # Done for good.
    form = {**body, 'email': 'eve@example.org'}
    again = await self_hosted.new_client().post(SETUP, json=form)
    assert (again.status_code, again.json()['error']) == (409, 'setup_done')


async def test_needs_the_setup_code(self_hosted: AppUnderTest) -> None:
    wrong = await self_hosted.client.post(SETUP, json=wizard(self_hosted, token='000000-000000-000000'))

    assert (wrong.status_code, wrong.json()['error']) == (403, 'invalid_setup_token')
    assert (await self_hosted.client.get(SETUP)).json() == {'open': True, 'self_hosted': True}


async def test_a_wrong_organization_undoes_the_whole_setup(self_hosted: AppUnderTest) -> None:
    refused = await self_hosted.client.post(SETUP, json=wizard(self_hosted, timezone='Mars/Olympus'))

    assert (refused.status_code, refused.json()['error']) == (422, 'invalid_timezone')
    assert (await self_hosted.client.get(SETUP)).json() == {'open': True, 'self_hosted': True}
    login = await self_hosted.client.post('/api/v1/auth/login', json={'email': 'ada@example.org', 'password': PASSWORD})
    assert login.status_code == 401
    # The code still works for the next try.
    assert (await self_hosted.client.post(SETUP, json=wizard(self_hosted))).status_code == 200


async def test_checks_the_administrator_like_any_account(self_hosted: AppUnderTest) -> None:
    weak = await self_hosted.client.post(SETUP, json=wizard(self_hosted, password='short'))

    assert (weak.status_code, weak.json()['error']) == (422, 'weak_password')


async def test_a_self_hosted_instance_has_one_organization(self_hosted: AppUnderTest) -> None:
    ada = self_hosted.new_client()
    assert (await ada.post(SETUP, json=wizard(self_hosted))).status_code == 200

    second = await ada.post(TENANTS, json={'name': 'Other GmbH'})

    assert (second.status_code, second.json()['error']) == (403, 'single_organization')


async def test_only_invited_people_sign_up_on_a_self_hosted_instance(self_hosted: AppUnderTest) -> None:
    ada = self_hosted.new_client()
    assert (await ada.post(SETUP, json=wizard(self_hosted))).status_code == 200
    [own] = (await ada.get(TENANTS)).json()

    closed = await self_hosted.client.post(
        '/api/v1/auth/register', json={'email': 'eve@example.org', 'password': PASSWORD}
    )
    assert (closed.status_code, closed.json()['error']) == (403, 'sign_up_closed')

    invited = await ada.post(f'{TENANTS}/{own["id"]}/invitations', json={'email': 'bob@example.org', 'role': 'agent'})
    assert invited.status_code == 201, invited.text
    invitation = self_hosted.mailer.last_token('bob@example.org')
    bob = await logged_in(self_hosted, 'bob@example.org')
    accepted = await bob.post('/api/v1/invitations/accept', json={'token': invitation})
    assert accepted.status_code == 200, accepted.text
    assert [each['name'] for each in (await bob.get(TENANTS)).json()] == ['Acme GmbH']


async def test_the_configured_administrator_creates_the_one_organization(
    services: Services, template_database: None, tmp_path: Path
) -> None:
    admin = InitialAdmin(email='ada@example.org', password=PASSWORD)
    async with running_app(
        services, tmp_path / 'data', 'test_configured_admin', multi_tenant=False, initial_admin=admin
    ) as app:
        assert (await app.client.get(SETUP)).json() == {'open': False, 'self_hosted': True}
        ada = app.new_client()
        login = await ada.post('/api/v1/auth/login', json={'email': 'ada@example.org', 'password': PASSWORD})
        assert login.status_code == 200, login.text

        await create_tenant(ada, 'Acme GmbH')
        second = await ada.post(TENANTS, json={'name': 'Other GmbH'})
        assert (second.status_code, second.json()['error']) == (403, 'single_organization')


async def test_saas_has_no_setup_wizard(app: AppUnderTest) -> None:
    assert (await app.client.get(SETUP)).json() == {'open': False, 'self_hosted': False}
    refused = await app.client.post(
        SETUP,
        json={
            'token': 'x',
            'email': 'ada@example.org',
            'password': PASSWORD,
            'organization_name': 'Acme GmbH',
            'timezone': 'Europe/Berlin',
        },
    )
    assert (refused.status_code, refused.json()['error']) == (409, 'setup_done')
    # Everyone signs up and makes as many organizations as they like.
    max_ = await logged_in(app, 'max@example.org')
    await create_tenant(max_, 'One GmbH')
    await create_tenant(max_, 'Two GmbH')
