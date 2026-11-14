from support.app import AppUnderTest
from support.helpdesk import posted, queue, ticket
from support.identity import logged_in
from support.tenancy import TENANTS, create_tenant, member_of


async def test_the_assistant_summarizes_and_drafts_replies(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    one = await ticket(ada, tenant, support)
    await posted(ada, f'{base}/tickets/{one["id"]}/messages', kind='internal', body='Toner is out of stock.')

    assert (await ada.get(f'{base}/assistant')).json() == {'enabled': True}
    app.writer.answer = 'Carl cannot print; toner is missing.'
    summary = await ada.post(f'{base}/tickets/{one["id"]}/assist', json={'task': 'summary'})
    assert summary.json() == {'text': 'Carl cannot print; toner is missing.'}
    asked = app.writer.asked[-1]
    assert (asked.task, asked.subject, asked.customer, asked.agent) == (
        'summary',
        'Printer broken',
        'Carl Customer',
        'ada@example.org',
    )
    assert [(each.from_customer, each.internal, each.body) for each in asked.lines] == [
        (True, False, 'It does not print.'),
        (False, True, 'Toner is out of stock.'),
    ]
    assert (await ada.post(f'{base}/tickets/{one["id"]}/assist', json={'task': 'reply'})).status_code == 200
    # Nothing was written to the ticket.
    assert len((await ada.get(f'{base}/tickets/{one["id"]}/messages')).json()) == 2

    assert (await ada.post(f'{base}/tickets/{one["id"]}/assist', json={'task': 'poem'})).status_code == 422
    app.writer.failure = 'refused'
    failed = (await ada.post(f'{base}/tickets/{one["id"]}/assist', json={'task': 'summary'})).json()
    assert (failed['error'], failed['params']) == ('assistant_failed', {'reason': 'refused'})

    # Only for tickets the member may see.
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    assert (await bob.post(f'{base}/tickets/{one["id"]}/assist', json={'task': 'summary'})).json()['error'] == (
        'ticket_not_found'
    )


async def test_the_assistant_is_limited_and_can_be_off(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    one = await ticket(ada, tenant, await queue(ada, tenant))
    for _ in range(30):
        await ada.post(f'{base}/tickets/{one["id"]}/assist', json={'task': 'summary'})
    busy = await ada.post(f'{base}/tickets/{one["id"]}/assist', json={'task': 'summary'})
    assert (busy.status_code, busy.json()['error']) == (429, 'assistant_busy')

    app.writer.enabled = False
    assert (await ada.get(f'{base}/assistant')).json() == {'enabled': False}
    off = await ada.post(f'{base}/tickets/{one["id"]}/assist', json={'task': 'summary'})
    assert (off.status_code, off.json()['error']) == (503, 'assistant_off')
