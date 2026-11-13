from typing import Any

import httpx

from .app import AppUnderTest
from .identity import logged_in

TENANTS = '/api/v1/tenants'


async def create_tenant(client: httpx.AsyncClient, name: str = 'Acme GmbH', **fields: Any) -> str:
    response = await client.post(TENANTS, json={'name': name, **fields})
    assert response.status_code == 201, response.text
    return str(response.json()['id'])


async def member_of(
    app: AppUnderTest, tenant_id: str, owner: httpx.AsyncClient, email: str, role: str
) -> httpx.AsyncClient:
    """A logged-in client of a new account that joined the tenant by invitation, with `role`."""
    response = await owner.post(f'{TENANTS}/{tenant_id}/invitations', json={'email': email, 'role': role})
    assert response.status_code == 201, response.text
    token = app.mailer.last_token(email)
    client = await logged_in(app, email)
    accepted = await client.post('/api/v1/invitations/accept', json={'token': token})
    assert accepted.status_code == 200, accepted.text
    return client


async def user_id_of(client: httpx.AsyncClient) -> str:
    return str((await client.get('/api/v1/account')).json()['id'])
