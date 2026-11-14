import re

from support.app import AppUnderTest
from support.helpdesk import posted, queue, ticket
from support.identity import logged_in
from support.portal import PORTAL, sign_in
from support.tenancy import TENANTS, create_tenant


async def test_customers_see_and_answer_their_tickets(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    await posted(ada, f'{base}/companies', name='Acme', domain='acme.example')
    mine = await ticket(ada, tenant, support, 'Printer broken', customer={'email': 'carl@acme.example', 'name': 'Carl'})
    colleague = await ticket(ada, tenant, support, 'Scanner', customer={'email': 'dora@acme.example'})
    await ticket(ada, tenant, support, 'Other', customer={'email': 'eve@else.example'})
    await posted(ada, f'{base}/tickets/{mine["id"]}/messages', kind='internal', body='Secret note')
    await posted(ada, f'{base}/tickets/{mine["id"]}/messages', kind='public', body='Please restart it.')

    # Closed until switched on.
    closed = await app.client.post(f'{PORTAL}/{tenant}/login', json={'email': 'carl@acme.example'})
    assert closed.json()['error'] == 'portal_closed'
    refused = await ada.put(f'{base}/portal-settings', json={'enabled': True})
    assert refused.json()['params'] == {'field': 'queue_id'}
    saved = await ada.put(f'{base}/portal-settings', json={'enabled': True, 'queue_id': support})
    assert saved.json() == {'enabled': True, 'queue_id': support, 'company_tickets': False}

    carl = await sign_in(app, tenant, 'carl@acme.example')
    me = (await carl.get(f'{PORTAL}/{tenant}/me')).json()
    assert (me['name'], me['company_name'], me['company_tickets']) == ('Carl', 'Acme', False)
    listed = (await carl.get(f'{PORTAL}/{tenant}/tickets')).json()
    assert [each['subject'] for each in listed] == ['Printer broken']
    thread = (await carl.get(f'{PORTAL}/{tenant}/tickets/{mine["id"]}')).json()
    assert [(each['from_customer'], each['body']) for each in thread['messages']] == [
        (True, 'It does not print.'),
        (False, 'Please restart it.'),
    ]
    assert thread['messages'][1]['author_name'] == 'ada'
    assert (await carl.get(f'{PORTAL}/{tenant}/tickets/{colleague["id"]}')).json()['error'] == 'ticket_not_found'

    answered = (
        await carl.post(f'{PORTAL}/{tenant}/tickets/{mine["id"]}/messages', data={'body': 'Still broken'})
    ).json()
    assert answered['messages'][-1] == {**answered['messages'][-1], 'from_customer': True, 'body': 'Still broken'}
    opened = await carl.post(f'{PORTAL}/{tenant}/tickets', data={'subject': 'New request', 'body': 'Need toner'})
    assert opened.status_code == 201
    staff = (await ada.get(f'{base}/tickets/{opened.json()["id"]}')).json()
    assert (staff['queue_id'], staff['channel'], staff['customer']['email']) == (support, 'web', 'carl@acme.example')
    assert (await carl.post(f'{PORTAL}/{tenant}/tickets', data={'subject': ' ', 'body': 'x'})).json()['error'] == (
        'invalid_portal'
    )
    assert (await carl.post(f'{PORTAL}/{tenant}/tickets/{colleague["id"]}/messages', data={'body': 'x'})).json()[
        'error'
    ] == 'ticket_not_found'

    # The company's tickets, once allowed.
    await ada.put(f'{base}/portal-settings', json={'enabled': True, 'queue_id': support, 'company_tickets': True})
    assert {each['subject'] for each in (await carl.get(f'{PORTAL}/{tenant}/tickets')).json()} == {
        'Printer broken',
        'Scanner',
        'New request',
    }

    assert (await carl.post(f'{PORTAL}/{tenant}/logout')).status_code == 204
    assert (await carl.get(f'{PORTAL}/{tenant}/me')).json()['error'] == 'portal_login_required'


async def test_sign_in_links_tell_nothing_and_work_once(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    await ticket(ada, tenant, support, customer={'email': 'carl@acme.example'})
    await ada.put(f'{base}/portal-settings', json={'enabled': True, 'queue_id': support})

    stranger = await app.client.post(f'{PORTAL}/{tenant}/login', json={'email': 'nobody@else.example'})
    assert stranger.status_code == 202
    assert app.mailer.to('nobody@else.example') == []
    await app.client.post(f'{PORTAL}/{tenant}/login', json={'email': 'not an address'})

    customer = app.new_client()
    await customer.post(f'{PORTAL}/{tenant}/login', json={'email': 'carl@acme.example'})
    token = re.search(r'token=([\w-]+)', app.mailer.to('carl@acme.example')[-1].text)
    assert token is not None
    assert (await customer.post(f'{PORTAL}/{tenant}/verify', json={'token': token.group(1)})).status_code == 200
    again = await customer.post(f'{PORTAL}/{tenant}/verify', json={'token': token.group(1)})
    assert again.json()['error'] == 'portal_link_invalid'

    await customer.post(f'{PORTAL}/{tenant}/login', json={'email': 'carl@acme.example'})
    late = re.search(r'token=([\w-]+)', app.mailer.to('carl@acme.example')[-1].text)
    assert late is not None
    app.clock.advance(minutes=31)
    assert (await app.client.post(f'{PORTAL}/{tenant}/verify', json={'token': late.group(1)})).json()['error'] == (
        'portal_link_invalid'
    )

    # Switching the portal off ends the sessions; another organization's path does not take them.
    other = await create_tenant(ada, 'Beta AG')
    assert (await customer.get(f'{PORTAL}/{other}/me')).json()['error'] == 'portal_login_required'
    await ada.put(f'{base}/portal-settings', json={'enabled': False})
    assert (await customer.get(f'{PORTAL}/{tenant}/me')).json()['error'] == 'portal_login_required'
    assert (await ada.get(f'{base}/portal-settings')).json()['enabled'] is False
    for _ in range(5):
        await app.client.post(f'{PORTAL}/{tenant}/login', json={'email': 'carl@acme.example'})
