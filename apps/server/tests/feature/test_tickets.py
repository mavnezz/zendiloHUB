from typing import Any

import httpx

from support.app import AppUnderTest
from support.helpdesk import grant, posted, queue, ticket
from support.identity import logged_in
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of

WORK = ['view', 'create', 'note', 'reply', 'edit']


async def desk(app: AppUnderTest) -> tuple[httpx.AsyncClient, str, str, str]:
    """Ada owns an organization with the queue Support; she sees every queue (queues.all)."""
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    return ada, tenant, f'{TENANTS}/{tenant}', await queue(ada, tenant)


async def history_of(client: httpx.AsyncClient, base: str, ticket_id: str) -> list[tuple[Any, ...]]:
    entries = (await client.get(f'{base}/tickets/{ticket_id}/history')).json()
    return [(entry['action'], entry['field'], entry['old'], entry['new']) for entry in entries]


async def test_works_a_ticket_from_the_first_call_to_the_reply(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)

    created = await ticket(ada, tenant, support, channel='phone', tags=['Printer', ' urgent '], priority='high')
    assert (created['number'], created['state'], created['priority'], created['channel']) == (
        1001,
        'new',
        'high',
        'phone',
    )
    assert created['tags'] == ['printer', 'urgent']
    assert (created['customer']['name'], created['customer']['email']) == ('Carl Customer', 'carl@customer.example')
    assert created['rights'] == ['view', 'create', 'note', 'reply', 'edit', 'assign', 'move']
    assert created['last_message_at'] is not None
    path = f'{base}/tickets/{created["id"]}'

    reply = await posted(
        ada, f'{path}/messages', kind='public', body=' Have you tried turning it off? ', time_minutes=5
    )
    assert (reply['direction'], reply['author_name'], reply['body']) == (
        'out',
        'ada@example.org',
        'Have you tried turning it off?',
    )
    await posted(ada, f'{path}/messages', kind='internal', body='Probably the toner.')
    app.clock.advance(hours=1)
    await posted(ada, f'{path}/messages', kind='public', direction='in', body='Still broken.')

    shown = (await ada.get(path)).json()
    assert (shown['state'], shown['time_minutes']) == ('open', 5)
    assert shown['first_response_at'] is not None
    messages = (await ada.get(f'{path}/messages')).json()
    assert [(each['kind'], each['direction'], each['author_kind']) for each in messages] == [
        ('public', 'in', 'customer'),
        ('public', 'out', 'agent'),
        ('internal', 'out', 'agent'),
        ('public', 'in', 'customer'),
    ]
    assert messages[0]['author_id'] == created['customer']['id']
    assert (await ada.get(f'{path}/time')).json()[0]['minutes'] == 5

    # Waiting for the customer needs a date; when it has come, the ticket is due.
    undated = (await ada.patch(path, json={'state': 'pending_reminder'})).json()
    assert (undated['error'], undated['params']) == ('invalid_ticket', {'field': 'pending_until'})
    waiting = await ada.patch(path, json={'state': 'pending_reminder', 'pending_until': '2026-10-24T09:00:00+00:00'})
    assert waiting.json()['state'] == 'pending_reminder'
    assert (await ada.get(f'{base}/tickets/counts')).json() == {
        'mine': 0,
        'unassigned': 1,
        'due': 0,
        'open': 1,
        'watching': 0,
    }
    app.clock.advance(days=3)
    assert [each['number'] for each in (await ada.get(f'{base}/tickets', params={'view': 'due'})).json()['items']] == [
        1001
    ]

    # A customer's answer opens it again.
    await posted(ada, f'{path}/messages', kind='public', direction='in', body='Any news?')
    shown = (await ada.get(path)).json()
    assert (shown['state'], shown['pending_until']) == ('open', None)
    closed = await posted(ada, f'{path}/messages', status=201, kind='public', body='Fixed, closing.', state='closed')
    assert closed['kind'] == 'public'
    shown = (await ada.get(path)).json()
    assert shown['state'] == 'closed'
    assert shown['closed_at'] is not None
    assert (await ada.get(f'{base}/tickets', params={'view': 'closed'})).json()['total'] == 1

    assert ('created', None, None, '1001') in await history_of(ada, base, created['id'])
    assert ('changed', 'state', 'new', 'open') in await history_of(ada, base, created['id'])
    assert ('time', None, None, '5') in await history_of(ada, base, created['id'])


async def test_the_groups_rights_decide_what_someone_may_do(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    billing = await queue(ada, tenant, 'Billing')
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    cleo = await member_of(app, tenant, ada, 'cleo@example.org', 'agent')
    dan = await member_of(app, tenant, ada, 'dan@example.org', 'agent')
    bob_id, cleo_id = await user_id_of(bob), await user_id_of(cleo)
    await grant(ada, tenant, support, [bob_id], WORK, name='Workers')
    await grant(ada, tenant, support, [cleo_id], ['view'], name='Readers')
    created = await ticket(ada, tenant, support)
    path = f'{base}/tickets/{created["id"]}'

    # Dan is in no group: there are no tickets for him.
    assert (await dan.get(path)).json()['error'] == 'ticket_not_found'
    assert (await dan.get(f'{base}/tickets', params={'view': 'all'})).json() == {'items': [], 'total': 0}
    assert (await dan.post(f'{base}/tickets', json={'queue_id': support, 'subject': 'X', 'body': 'Y'})).json()[
        'error'
    ] == 'queue_right_missing'

    # Cleo may read, not write.
    assert (await cleo.get(path)).json()['rights'] == ['view']
    refused = (await cleo.post(f'{path}/messages', json={'kind': 'internal', 'body': 'Hm'})).json()
    assert (refused['error'], refused['params']) == ('queue_right_missing', {'right': 'note'})
    assert (await cleo.patch(path, json={'priority': 'low'})).json()['params'] == {'right': 'edit'}

    # Bob works in the queue: he takes the ticket, but may not hand it to others (no `assign`).
    assert (await bob.patch(path, json={'owner_id': bob_id})).json()['owner_id'] == bob_id
    assert (await bob.patch(path, json={'owner_id': cleo_id})).json()['params'] == {'right': 'assign'}
    assert (await bob.patch(path, json={'queue_id': billing})).json()['params'] == {'right': 'move'}
    assert (await bob.get(f'{base}/tickets', params={'view': 'mine'})).json()['total'] == 1
    assert (await bob.patch(path, json={'owner_id': None})).json()['owner_id'] is None

    # Ada (every right) hands it out, but only to people who may reply in the queue.
    assert (await ada.patch(path, json={'owner_id': cleo_id})).json()['error'] == 'not_assignable'
    assert (await ada.get(f'{base}/queues/{support}/assignees')).json() == [await user_id_of(ada), bob_id]
    assert (await ada.patch(path, json={'owner_id': bob_id, 'responsible_id': cleo_id})).json()['owner_id'] == bob_id
    assert (await dan.get(f'{base}/queues/{support}/assignees')).json()['error'] == 'ticket_not_found'

    # Moving to a queue where Bob may not reply takes the ticket from him.
    moved = (await ada.patch(path, json={'queue_id': billing})).json()
    assert (moved['queue_id'], moved['owner_id']) == (billing, None)
    assert (await bob.get(path)).json()['error'] == 'ticket_not_found'

    # Without `tickets.delete` nobody deletes tickets; Ada (owner) may.
    assert (await bob.delete(path)).status_code == 403
    assert (await ada.delete(path)).status_code == 204
    assert (await ada.get(path)).json()['error'] == 'ticket_not_found'


async def test_finds_tickets_by_views_filters_and_text(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    ada_id = await user_id_of(ada)
    company = await posted(ada, f'{base}/companies', name='Acme', domain='acme.example')
    first = await ticket(
        ada, tenant, support, 'Invoice missing', tags=['billing'], customer={'email': 'x@acme.example'}
    )
    second = await ticket(ada, tenant, support, 'Login fails', priority='urgent', owner_id=ada_id)
    await posted(ada, f'{base}/tickets/{second["id"]}/messages', kind='internal', body='The password expired')

    async def numbers(**params: Any) -> list[int]:
        found = (await ada.get(f'{base}/tickets', params=params)).json()
        return [each['number'] for each in found['items']]

    assert await numbers() == [1002, 1001]
    assert await numbers(view='mine') == [1002]
    assert await numbers(view='unassigned') == [1001]
    assert await numbers(q='#1001') == [1001]
    assert await numbers(q='invoice') == [1001]
    assert await numbers(q='expired') == [1002]
    assert await numbers(tag='Billing') == [1001]
    assert await numbers(priority='urgent') == [1002]
    assert await numbers(company_id=company['id']) == [1001]
    assert await numbers(customer_id=first['customer']['id']) == [1001]
    assert await numbers(view='all', ids=[second['id']]) == [1002]
    assert await numbers(sort='priority') == [1002, 1001]
    assert await numbers(sort='number', descending='false') == [1001, 1002]
    assert await numbers(owner_id=ada_id, queue_id=support, state='new') == [1002]
    found = (await ada.get(f'{base}/tickets/by-number/1001')).json()
    assert found['id'] == first['id']
    assert (await ada.get(f'{base}/tickets/by-number/9')).json()['error'] == 'ticket_not_found'


async def test_watches_links_merges_and_splits(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    bob_id = await user_id_of(bob)
    await grant(ada, tenant, support, [bob_id], WORK)
    one = await ticket(ada, tenant, support, 'First mail', tags=['a'])
    two = await ticket(ada, tenant, support, 'Second mail', tags=['b'])
    one_path, two_path = f'{base}/tickets/{one["id"]}', f'{base}/tickets/{two["id"]}'

    assert (await bob.put(f'{one_path}/watch')).status_code == 204
    assert (await bob.get(one_path)).json()['watching'] is True
    assert (await bob.get(f'{base}/tickets', params={'view': 'watching'})).json()['total'] == 1
    assert (await bob.delete(f'{one_path}/watch')).status_code == 204
    # Mentioning someone in a note makes them watch.
    await posted(ada, f'{two_path}/messages', kind='internal', body='@bob please look', mentions=[bob_id])
    assert (await ada.get(two_path)).json()['watchers'] == [bob_id]
    stranger_id = await user_id_of(await logged_in(app, 'eve@example.org'))
    bad = (
        await ada.post(f'{two_path}/messages', json={'kind': 'internal', 'body': 'x', 'mentions': [stranger_id]})
    ).json()
    assert (bad['error'], bad['params']) == ('invalid_message', {'field': 'mentions'})

    linked = await posted(ada, f'{one_path}/links', number=two['number'], kind='parent')
    assert linked['links'] == [
        {'id': two['id'], 'number': two['number'], 'subject': 'Second mail', 'state': 'new', 'kind': 'parent'}
    ]
    assert (await ada.get(two_path)).json()['links'][0]['kind'] == 'child'
    assert (await ada.post(f'{one_path}/links', json={'number': one['number']})).json()['error'] == 'link_to_itself'
    assert (await ada.delete(f'{one_path}/links/{two["id"]}')).status_code == 204
    assert (await ada.get(one_path)).json()['links'] == []
    assert (await ada.delete(f'{one_path}/links/{two["id"]}')).json()['error'] == 'ticket_not_found'

    # The customer wrote twice: one goes into two, with its messages, tags and watchers.
    await ada.put(f'{one_path}/watch')
    merged = await posted(ada, f'{one_path}/merge', status=200, number=two['number'])
    assert (merged['id'], merged['tags'], len(merged['watchers'])) == (two['id'], ['a', 'b'], 2)
    assert len((await ada.get(f'{two_path}/messages')).json()) == 3
    left = (await ada.get(one_path)).json()
    assert (left['state'], left['merged_into']) == ('merged', {'id': two['id'], 'number': two['number']})
    assert (await ada.post(f'{one_path}/messages', json={'kind': 'internal', 'body': 'x'})).json()[
        'error'
    ] == 'ticket_merged'
    assert (await ada.patch(one_path, json={'priority': 'low'})).json()['error'] == 'ticket_merged'
    assert (await ada.post(f'{two_path}/merge', json={'number': two['number']})).json()['error'] == 'merge_into_itself'
    assert (await ada.post(f'{two_path}/merge', json={'number': one['number']})).json()['error'] == 'ticket_merged'
    assert (await ada.get(f'{base}/tickets', params={'view': 'all'})).json()['total'] == 1
    assert ('merged', None, None, str(two['number'])) in await history_of(ada, base, one['id'])

    # A second concern in one message becomes a ticket of its own.
    message_id = (await ada.get(f'{two_path}/messages')).json()[0]['id']
    split = await posted(ada, f'{two_path}/split', message_id=message_id, subject='Separate issue')
    assert (split['subject'], split['customer']['id'], split['links'][0]['id']) == (
        'Separate issue',
        two['customer']['id'],
        two['id'],
    )
    assert (await ada.get(f'{base}/tickets/{split["id"]}/messages')).json()[0]['body'] == 'It does not print.'
    missing = '0196f3c0-0000-7000-8000-000000000009'
    assert (await ada.post(f'{two_path}/split', json={'message_id': missing})).json()['error'] == 'message_not_found'

    time = await posted(bob, f'{two_path}/time', minutes=15)
    assert time['user_id'] == bob_id
    assert (await ada.get(two_path)).json()['time_minutes'] == 15


async def test_changes_many_tickets_at_once(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    billing = await queue(ada, tenant, 'Billing')
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    await grant(ada, tenant, support, [await user_id_of(bob)], ['view', 'edit'])
    one = await ticket(ada, tenant, support)
    two = await ticket(ada, tenant, billing)

    done = await posted(
        bob, f'{base}/tickets/bulk', status=200, ticket_ids=[one['id'], two['id']], priority='low', add_tags=['batch']
    )
    assert done == {'changed': [one['id']], 'failed': {two['id']: 'ticket_not_found'}}
    shown = (await ada.get(f'{base}/tickets/{one["id"]}')).json()
    assert (shown['priority'], shown['tags']) == ('low', ['batch'])
    moved = await posted(ada, f'{base}/tickets/bulk', status=200, ticket_ids=[one['id']], queue_id=billing)
    assert moved['changed'] == [one['id']]


async def test_closes_pending_tickets_on_their_date(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    created = await ticket(ada, tenant, support, state='pending_close', pending_until='2026-10-23T12:00:00+00:00')
    assert created['state'] == 'pending_close'

    app.clock.advance(days=2)
    await app.app.context.scheduler.run_all()

    shown = (await ada.get(f'{base}/tickets/{created["id"]}')).json()
    assert shown['state'] == 'closed'
    assert ('changed', 'state', 'pending_close', 'closed') in await history_of(ada, base, created['id'])
    entries = (await ada.get(f'{base}/tickets/{created["id"]}/history')).json()
    assert entries[-1]['actor_name'] == 'zendiloHUB'


async def test_checks_tickets(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    missing = '0196f3c0-0000-7000-8000-000000000009'

    async def error(**body: Any) -> tuple[str, Any]:
        answer = (
            await ada.post(f'{base}/tickets', json={'queue_id': support, 'subject': 'S', 'body': 'B', **body})
        ).json()
        return answer['error'], answer.get('params')

    assert await error(subject=' ') == ('invalid_ticket', {'field': 'subject'})
    assert await error(tags=['no!']) == ('invalid_ticket', {'field': 'tags'})
    assert await error(body=' ') == ('invalid_message', {'field': 'body'})
    assert await error(customer={'id': missing}) == ('invalid_ticket', {'field': 'customer'})
    assert await error(customer={'name': 'Nobody'}) == ('invalid_ticket', {'field': 'customer'})
    assert await error(customer={'email': 'bad'}) == ('invalid_contact', {'field': 'email'})
    assert (await error(time_minutes=0))[0] == 'invalid_request'
    created = await ticket(ada, tenant, support, first='note', customer={'phone': '+49 30 1'})
    assert created['state'] == 'new'
    reply_first = await ticket(ada, tenant, support, first='reply')
    assert reply_first['state'] == 'open'
    path = f'{base}/tickets/{created["id"]}'
    assert (await ada.patch(path, json={'customer_id': missing})).json()['params'] == {'field': 'customer_id'}
    assert (await ada.patch(path, json={'responsible_id': missing})).json()['params'] == {'field': 'responsible_id'}
    assert (await ada.patch(path, json={'customer_id': None, 'subject': 'New'})).json()['customer'] is None
    assert (await ada.patch(path, json={'pending_until': '2026-11-01T00:00:00+00:00'})).json()['pending_until'] is None
    assert (await ada.post(f'{path}/time', json={'minutes': 2000})).status_code == 422
    assert (await ada.post(f'{path}/messages', json={'kind': 'internal', 'direction': 'in', 'body': 'x'})).json()[
        'params'
    ] == {'field': 'direction'}


async def test_api_keys_need_every_queue_and_people_who_leave_lose_their_tickets(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'admin')
    bob_id = await user_id_of(bob)
    await grant(ada, tenant, support, [bob_id], WORK)
    created = await ticket(ada, tenant, support, owner_id=bob_id)

    # Admins may not see every queue, so they cannot make a key that may.
    refused = await bob.post(f'{base}/api-keys', json={'name': 'Bot', 'permissions': ['queues.all']})
    assert refused.json()['error'] == 'role_exceeds_own'
    all_queues = await posted(ada, f'{base}/api-keys', name='Bot', permissions=['queues.all'])
    blind = await posted(bob, f'{base}/api-keys', name='Blind', permissions=['customers.view'])
    key = app.new_client()
    key.headers['Authorization'] = f'Bearer {all_queues["key"]}'
    assert (await key.get(f'{base}/tickets')).json()['total'] == 1
    assert (await posted(key, f'{base}/tickets/{created["id"]}/messages', kind='internal', body='From the bot'))[
        'author_name'
    ] == 'API key: Bot'
    key.headers['Authorization'] = f'Bearer {blind["key"]}'
    assert (await key.get(f'{base}/tickets')).json()['total'] == 0

    # Queues with tickets stay.
    refused_queue = (await ada.delete(f'{base}/queues/{support}')).json()
    assert (refused_queue['error'], refused_queue['params']) == ('queue_has_tickets', {'count': 1})

    assert (await ada.delete(f'{base}/members/{bob_id}')).status_code == 204
    assert (await ada.get(f'{base}/tickets/{created["id"]}')).json()['owner_id'] is None


async def test_tickets_go_with_their_organization(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    await ticket(ada, tenant, support)

    assert (await ada.delete(base)).status_code == 204

    async with app.app.context.db.connection() as connection:
        row = await (await connection.execute('SELECT count(*) AS n FROM tickets')).fetchone()
    assert row is not None
    assert row['n'] == 0
