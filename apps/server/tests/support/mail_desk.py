"""An organization with a queue and its e-mail account, for the tests of e-mails."""

from typing import Any

import httpx

from .app import AppUnderTest
from .helpdesk import posted, queue
from .identity import logged_in
from .tenancy import TENANTS, create_tenant

SUPPORT = 'support@acme.example'


def account_body(queue_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        'name': 'Support',
        'address': SUPPORT,
        'display_name': 'Acme Support',
        'queue_id': queue_id,
        'imap': {'host': 'imap.acme.example', 'port': 993, 'security': 'ssl', 'username': SUPPORT, 'password': 'pw'},
        'smtp': {
            'host': 'smtp.acme.example',
            'port': 587,
            'security': 'starttls',
            'username': SUPPORT,
            'password': 'pw',
        },
        **overrides,
    }


async def mail_desk(app: AppUnderTest) -> tuple[httpx.AsyncClient, str, str, str, dict[str, Any]]:
    """Ada's organization with the queue Support and its account support@ (which also sends its replies)."""
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    account = await posted(ada, f'{base}/email-accounts', **account_body(support))
    answer = await ada.put(f'{base}/queue-channels/{support}', json={'account_id': account['id']})
    assert answer.status_code == 200, answer.text
    return ada, tenant, base, support, account


async def fetch(app: AppUnderTest) -> None:
    await app.app.context.scheduler.run_all()
    await app.run_jobs()


async def tickets(client: httpx.AsyncClient, base: str) -> list[dict[str, Any]]:
    return list((await client.get(f'{base}/tickets', params={'view': 'all'})).json()['items'])
