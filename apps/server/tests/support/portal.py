"""Customers signed in to the portal, for its tests."""

import re

import httpx

from .app import AppUnderTest

PORTAL = '/api/v1/portal'


async def sign_in(app: AppUnderTest, tenant: str, email: str) -> httpx.AsyncClient:
    customer = app.new_client()
    assert (await customer.post(f'{PORTAL}/{tenant}/login', json={'email': email})).status_code == 202
    link = app.mailer.to(email)[-1].text
    token = re.search(r'token=([\w-]+)', link)
    assert token is not None
    verified = await customer.post(f'{PORTAL}/{tenant}/verify', json={'token': token.group(1)})
    assert verified.status_code == 200, verified.text
    return customer
