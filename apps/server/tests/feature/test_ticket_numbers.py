import asyncio
from datetime import UTC, datetime

from support.app import AppUnderTest
from support.helpdesk import posted, queue, ticket
from support.identity import logged_in
from support.mail_desk import SUPPORT, fetch, mail_desk, tickets
from support.mail_server import email
from support.tenancy import TENANTS, create_tenant, member_of


async def test_numbers_start_where_the_organization_wants_and_only_grow(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    support = await queue(ada, tenant)
    path = f'{TENANTS}/{tenant}/ticket-numbers'

    assert (await ada.get(path)).json() == {
        'format': 'increment',
        'start': 1001,
        'date_digits': 4,
        'checksum': False,
        'prefix': '#',
        'next_number': 1001,
        'next_tag': '[#1001]',
    }
    assert (await ticket(ada, tenant, support))['number'] == 1001

    lower = (await ada.put(path, json={'start': 500})).json()
    assert (lower['error'], lower['params']) == ('invalid_numbering', {'field': 'start', 'minimum': 1002})
    raised = (await ada.put(path, json={'start': 5000, 'prefix': ' Ticket# '})).json()
    assert (raised['next_number'], raised['next_tag']) == (5000, '[Ticket#5000]')
    assert [(await ticket(ada, tenant, support))['number'] for _ in range(2)] == [5000, 5001]

    # The same start again is fine, though it lies below the last number now.
    checked = (await ada.put(path, json={'start': 5000, 'checksum': True, 'prefix': 'Ticket#'})).json()
    assert checked['next_number'] == 50021
    assert (await ticket(ada, tenant, support))['number'] == 50021
    found = (await ada.get(f'{TENANTS}/{tenant}/tickets', params={'q': '#50021', 'view': 'all'})).json()
    assert [each['number'] for each in found['items']] == [50021]

    for body, field in [({'prefix': 'a b'}, 'prefix'), ({'prefix': '[x]'}, 'prefix')]:
        refused = (await ada.put(path, json=body)).json()
        assert (refused['error'], refused['params']) == ('invalid_numbering', {'field': field})
    assert (await ada.put(path, json={'date_digits': 9})).status_code == 422
    agent = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    assert (await agent.get(path)).status_code == 403
    log = {entry['action'] for entry in (await ada.get(f'{TENANTS}/{tenant}/audit-log')).json()['items']}
    assert 'ticket_numbers.changed' in log


async def test_date_numbers_count_per_day_of_the_organization(app: AppUnderTest) -> None:
    app.clock.current = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada, timezone='Europe/Berlin')
    support = await queue(ada, tenant)
    path = f'{TENANTS}/{tenant}/ticket-numbers'

    assert (await ada.put(path, json={'format': 'date', 'date_digits': 3})).json()['next_number'] == 20261022001
    assert [(await ticket(ada, tenant, support))['number'] for _ in range(2)] == [20261022001, 20261022002]
    # 22:30 in UTC is half past midnight in Berlin: a new day there.
    app.clock.current = datetime(2026, 10, 22, 22, 30, tzinfo=UTC)
    assert (await ticket(ada, tenant, support))['number'] == 20261023001

    # Back to counting up: from the start, never onto a number that exists.
    assert (await ada.put(path, json={'format': 'increment'})).json()['next_number'] == 1001
    assert (await ticket(ada, tenant, support))['number'] == 1001


async def test_parallel_tickets_never_share_a_number(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    support = await queue(ada, tenant)

    created = await asyncio.gather(
        *(
            ticket(ada, tenant, support, customer={'email': f'c{index}@customer.example', 'name': 'C'})
            for index in range(12)
        )
    )

    assert sorted(each['number'] for each in created) == list(range(1001, 1013))


async def test_mails_carry_the_prefix_and_answers_find_the_ticket_by_old_and_new_tags(app: AppUnderTest) -> None:
    ada, _tenant, base, support, account = await mail_desk(app)
    await ada.put(
        f'{base}/queue-channels/{support}',
        json={
            'account_id': account['id'],
            'auto_reply': True,
            'auto_reply_subject': 'Received: {{ticket.subject}}',
            'auto_reply_body': 'Your ticket number is {{ticket.number}}.',
        },
    )
    await ada.put(f'{base}/ticket-numbers', json={'prefix': 'Ticket#'})
    app.mail.deliver(SUPPORT, email())
    await fetch(app)
    [created] = await tickets(ada, base)
    path = f'{base}/tickets/{created["id"]}'

    [(_, auto)] = app.mail.sent
    assert (auto.subject, auto.text) == ('Received: Printer broken [Ticket#1001]', 'Your ticket number is 1001.')
    await posted(ada, f'{path}/messages', kind='public', body='Please restart it.')
    await app.run_jobs()
    assert app.mail.sent[-1][1].subject == 'Re: Printer broken [Ticket#1001]'

    app.mail.deliver(SUPPORT, email(subject='Any news? [Ticket#1001]', message_id='<n1@customer.example>'))
    app.mail.deliver(SUPPORT, email(subject='Re: Printer broken [#1001]', message_id='<n2@customer.example>'))
    app.mail.deliver(SUPPORT, email(subject='Other [ZH-1001]', message_id='<n3@customer.example>'))
    await fetch(app)

    assert len(await tickets(ada, base)) == 2
    assert len((await ada.get(f'{path}/messages')).json()) == 4
