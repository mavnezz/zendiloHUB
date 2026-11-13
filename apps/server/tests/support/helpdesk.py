from typing import Any

import httpx

from .tenancy import TENANTS


async def posted(client: httpx.AsyncClient, path: str, status: int = 201, **body: Any) -> dict[str, Any]:
    response = await client.post(path, json=body)
    assert response.status_code == status, response.text
    return dict(response.json())


async def queue(owner: httpx.AsyncClient, tenant_id: str, name: str = 'Support') -> str:
    return str((await posted(owner, f'{TENANTS}/{tenant_id}/queues', name=name))['id'])


async def grant(
    owner: httpx.AsyncClient, tenant_id: str, queue_id: str, user_ids: list[str], rights: list[str], name: str = 'Team'
) -> str:
    """A group of these people with these rights in the queue."""
    base = f'{TENANTS}/{tenant_id}'
    group = await posted(owner, f'{base}/groups', name=name)
    members = await owner.put(f'{base}/groups/{group["id"]}/members', json={'user_ids': user_ids})
    assert members.status_code == 200, members.text
    rights_set = await owner.put(
        f'{base}/queue-rights', json={'group_id': group['id'], 'queue_id': queue_id, 'rights': rights}
    )
    assert rights_set.status_code == 200, rights_set.text
    return str(group['id'])


async def ticket(
    client: httpx.AsyncClient, tenant_id: str, queue_id: str, subject: str = 'Printer broken', **fields: Any
) -> dict[str, Any]:
    body = {'queue_id': queue_id, 'subject': subject, 'body': 'It does not print.', **fields}
    body.setdefault('customer', {'email': 'carl@customer.example', 'name': 'Carl Customer'})
    return await posted(client, f'{TENANTS}/{tenant_id}/tickets', **body)
