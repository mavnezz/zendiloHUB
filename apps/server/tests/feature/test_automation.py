from typing import Any

import httpx

from support.app import AppUnderTest
from support.helpdesk import grant, posted, queue, ticket
from support.identity import logged_in
from support.mail_server import email
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of


async def desk(app: AppUnderTest) -> tuple[httpx.AsyncClient, str, str, str]:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    return ada, tenant, f'{TENANTS}/{tenant}', await queue(ada, tenant)


async def shown(client: httpx.AsyncClient, base: str, ticket_id: str) -> dict[str, Any]:
    return dict((await client.get(f'{base}/tickets/{ticket_id}')).json())


async def test_triggers_act_on_new_tickets_replies_and_changes(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    billing = await queue(ada, tenant, 'Billing')
    await posted(
        ada,
        f'{base}/triggers',
        name='Invoices to billing',
        event='created',
        conditions=[
            {'field': 'subject', 'operator': 'contains', 'value': 'invoice'},
            {'field': 'owner', 'operator': 'is_not_set'},
        ],
        actions={'queue_id': billing, 'priority': 'high', 'add_tags': ['Billing'], 'note': 'Routed by a trigger'},
    )
    await posted(
        ada,
        f'{base}/triggers',
        name='Reopened',
        event='customer_replied',
        conditions=[{'field': 'tags', 'operator': 'contains', 'value': 'billing'}],
        actions={'add_tags': ['answered']},
    )
    await posted(
        ada,
        f'{base}/triggers',
        name='Urgent means open',
        event='updated',
        conditions=[{'field': 'priority', 'operator': 'is', 'value': 'urgent'}],
        actions={'state': 'open', 'reply': 'We are on it.'},
    )
    await posted(
        ada,
        f'{base}/triggers',
        name='Off',
        active=False,
        event='created',
        actions={'add_tags': ['never']},
    )

    invoice = await ticket(ada, tenant, support, 'Invoice wrong')
    after = await shown(ada, base, invoice['id'])
    assert (after['queue_id'], after['priority'], after['tags']) == (billing, 'high', ['billing'])
    messages = (await ada.get(f'{base}/tickets/{invoice["id"]}/messages')).json()
    assert (messages[-1]['kind'], messages[-1]['author_kind'], messages[-1]['author_name']) == (
        'internal',
        'system',
        'Trigger: Invoices to billing',
    )
    history = (await ada.get(f'{base}/tickets/{invoice["id"]}/history')).json()
    assert ('Trigger: Invoices to billing', 'queue_id') in [(each['actor_name'], each['field']) for each in history]

    other = await ticket(ada, tenant, support, 'Printer')
    assert (await shown(ada, base, other['id']))['tags'] == []

    # The customer writes again: only the ticket with the tag gets the second one.
    await posted(ada, f'{base}/tickets/{invoice["id"]}/messages', kind='public', direction='in', body='Hello?')
    await posted(ada, f'{base}/tickets/{other["id"]}/messages', kind='public', direction='in', body='Hello?')
    assert (await shown(ada, base, invoice['id']))['tags'] == ['answered', 'billing']
    assert (await shown(ada, base, other['id']))['tags'] == []

    # Someone makes it urgent: the trigger replies (and does not run again on its own change).
    await ada.patch(
        f'{base}/tickets/{other["id"]}',
        json={'priority': 'urgent', 'state': 'pending_reminder', 'pending_until': '2026-11-01T00:00:00+00:00'},
    )
    after = await shown(ada, base, other['id'])
    assert after['state'] == 'open'
    replies = [
        each
        for each in (await ada.get(f'{base}/tickets/{other["id"]}/messages')).json()
        if each['kind'] == 'public' and each['direction'] == 'out'
    ]
    assert [each['body'] for each in replies] == ['We are on it.']

    listed = (await ada.get(f'{base}/triggers')).json()
    assert [each['name'] for each in listed] == ['Invoices to billing', 'Reopened', 'Urgent means open', 'Off']


async def test_triggers_run_on_mail_too_and_bad_ones_do_not_stop_it(app: AppUnderTest) -> None:
    ada, _tenant, base, support = await desk(app)
    account = await posted(
        ada,
        f'{base}/email-accounts',
        name='Support',
        address='support@acme.example',
        queue_id=support,
        imap={'host': 'imap.acme.example', 'port': 993},
        smtp={'host': 'smtp.acme.example', 'port': 465},
    )
    assert account['active']
    await posted(
        ada,
        f'{base}/triggers',
        name='VIP',
        event='created',
        conditions=[{'field': 'customer_email', 'operator': 'contains', 'value': '@customer.example'}],
        actions={'priority': 'urgent', 'owner_id': await user_id_of(ada)},
    )
    app.mail.deliver('support@acme.example', email())
    await app.app.context.scheduler.run_all()
    await app.run_jobs()

    [created] = (await ada.get(f'{base}/tickets', params={'view': 'all'})).json()['items']
    assert (created['priority'], created['owner_id']) == ('urgent', await user_id_of(ada))


async def test_scheduled_jobs_close_what_waits_too_long(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    job = await posted(
        ada,
        f'{base}/scheduled-jobs',
        name='Close stale',
        schedule={'states': ['pending_reminder'], 'idle_hours': 72, 'queue_ids': [support]},
        actions={'state': 'closed', 'note': 'Closed after three days without an answer.'},
    )
    assert job['schedule']['idle_hours'] == 72
    waiting = await ticket(ada, tenant, support, state='pending_reminder', pending_until='2026-10-23T00:00:00+00:00')
    fresh = await ticket(
        ada, tenant, support, 'Fresh', state='pending_reminder', pending_until='2026-10-23T00:00:00+00:00'
    )
    app.clock.advance(hours=48)
    await ada.patch(f'{base}/tickets/{fresh["id"]}', json={'priority': 'high'})
    app.clock.advance(hours=25)

    await app.app.context.scheduler.run_all()

    assert (await shown(ada, base, waiting['id']))['state'] == 'closed'
    assert (await shown(ada, base, fresh['id']))['state'] == 'pending_reminder'
    assert (await ada.get(f'{base}/scheduled-jobs')).json()[0]['last_run_at'] is not None


async def test_macros_are_for_everyone_and_rules_are_checked(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    await grant(ada, tenant, support, [await user_id_of(bob)], ['view'])
    macro = await posted(
        ada,
        f'{base}/macros',
        name='Close as solved',
        actions={'state': 'closed', 'owner_me': True, 'add_tags': ['Solved'], 'note': 'Solved.'},
    )
    assert macro['actions']['add_tags'] == ['solved']
    assert [each['name'] for each in (await bob.get(f'{base}/macros')).json()] == ['Close as solved']
    assert (await bob.post(f'{base}/macros', json={'name': 'X', 'actions': {'state': 'open'}})).status_code == 403
    assert (await bob.get(f'{base}/triggers')).status_code == 403

    changed = await ada.patch(f'{base}/macros/{macro["id"]}', json={'name': 'Done', 'actions': {'state': 'closed'}})
    assert changed.json()['name'] == 'Done'
    for path, body, field in [
        ('macros', {'name': 'X', 'actions': {}}, 'actions'),
        ('macros', {'name': 'X', 'actions': {'reply': 'Hi'}}, 'actions.reply'),
        ('triggers', {'name': 'X', 'actions': {'owner_me': True}, 'event': 'created'}, 'actions.owner_me'),
        ('triggers', {'name': 'X', 'actions': {'state': 'open'}}, 'event'),
        (
            'triggers',
            {
                'name': 'X',
                'event': 'created',
                'actions': {'state': 'open'},
                'conditions': [{'field': 'subject', 'operator': 'contains'}],
            },
            'conditions.value',
        ),
        ('scheduled-jobs', {'name': 'X', 'actions': {'state': 'closed'}}, 'schedule'),
        ('scheduled-jobs', {'name': 'X', 'actions': {'state': 'closed'}, 'schedule': {}}, 'schedule'),
        ('macros', {'name': ' ', 'actions': {'state': 'open'}}, 'name'),
    ]:
        answer = (await ada.post(f'{base}/{path}', json=body)).json()
        assert (answer['error'], answer['params']) == ('invalid_rule', {'field': field}), path
    missing = '0196f3c0-0000-7000-8000-000000000009'
    assert (await ada.patch(f'{base}/macros/{missing}', json={'name': 'X', 'actions': {'state': 'open'}})).json()[
        'error'
    ] == 'rule_not_found'
    assert (await ada.delete(f'{base}/macros/{macro["id"]}')).status_code == 204
    assert (await ada.delete(f'{base}/macros/{macro["id"]}')).json()['error'] == 'rule_not_found'


async def test_text_modules_by_keyword_and_queue(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    billing = await queue(ada, tenant, 'Billing')
    thanks = await posted(ada, f'{base}/text-modules', name='Thanks', keyword=' Thanks ', body='Thank you for writing.')
    await posted(ada, f'{base}/text-modules', name='IBAN', keyword='iban', body='Our IBAN is …', queue_ids=[billing])
    assert thanks['keyword'] == 'thanks'
    everywhere = (await ada.get(f'{base}/text-modules')).json()
    assert [each['keyword'] for each in everywhere] == ['iban', 'thanks']
    in_support = (await ada.get(f'{base}/text-modules', params={'queue_id': support})).json()
    assert [each['keyword'] for each in in_support] == ['thanks']

    agent = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    assert len((await agent.get(f'{base}/text-modules')).json()) == 2
    assert (
        await agent.post(f'{base}/text-modules', json={'name': 'X', 'keyword': 'x', 'body': 'x'})
    ).status_code == 403
    manager = await member_of(app, tenant, ada, 'cleo@example.org', 'manager')
    assert (
        await manager.post(f'{base}/text-modules', json={'name': 'Bye', 'keyword': 'bye', 'body': 'Bye'})
    ).status_code == 201

    for body, error in [
        ({'name': 'X', 'keyword': 'thanks', 'body': 'x'}, 'keyword_taken'),
        ({'name': 'X', 'keyword': 'no spaces', 'body': 'x'}, 'invalid_text_module'),
        ({'name': ' ', 'keyword': 'y', 'body': 'x'}, 'invalid_text_module'),
        ({'name': 'X', 'keyword': 'y', 'body': ' '}, 'invalid_text_module'),
    ]:
        assert (await ada.post(f'{base}/text-modules', json=body)).json()['error'] == error
    renamed = await ada.patch(
        f'{base}/text-modules/{thanks["id"]}', json={'name': 'Thanks', 'keyword': 'ty', 'body': 'Thanks!'}
    )
    assert renamed.json()['keyword'] == 'ty'

    # A deleted queue leaves the modules limited to it for every queue.
    await ada.delete(f'{base}/queues/{billing}')
    assert [
        each['queue_ids'] for each in (await ada.get(f'{base}/text-modules')).json() if each['keyword'] == 'iban'
    ] == [[]]
    assert (await ada.delete(f'{base}/text-modules/{thanks["id"]}')).status_code == 204
    missing = '0196f3c0-0000-7000-8000-000000000009'
    assert (await ada.delete(f'{base}/text-modules/{missing}')).json()['error'] == 'text_module_not_found'
    assert (await ada.patch(f'{base}/text-modules/{missing}', json={'name': 'X', 'keyword': 'x', 'body': 'x'})).json()[
        'error'
    ] == 'text_module_not_found'
