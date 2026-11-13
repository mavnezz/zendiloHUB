import hashlib
import hmac
import json

from support.app import AppUnderTest
from support.helpdesk import posted, queue, ticket
from support.identity import logged_in
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of
from zendilohub.core.domain.http_fetch import FetchBlockedError, FetchFailedError

HOOK = 'https://crm.example/hooks/zendilohub'


async def test_webhooks_hear_about_tickets_signed_and_retried(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    app.websites.answer(HOOK, 204)

    created = await posted(ada, f'{base}/webhooks', name='CRM', url=HOOK, events=['message.added', 'ticket.created'])
    secret = created['secret']
    assert secret.startswith('whsec_')
    assert created['events'] == ['ticket.created', 'message.added']
    assert (await ada.get(f'{base}/webhooks')).json()[0]['secret'] is None

    one = await ticket(ada, tenant, support)
    await app.run_jobs()
    sent = app.websites.to(HOOK)
    assert [json.loads(each.body)['event'] for each in sent] == ['ticket.created', 'message.added']
    first = sent[0]
    expected = 'sha256=' + hmac.new(secret.encode(), first.body, hashlib.sha256).hexdigest()
    assert first.headers['X-Zendilohub-Signature'] == expected
    payload = json.loads(first.body)
    assert (payload['tenant_id'], payload['data']['ticket']['number']) == (tenant, one['number'])

    # Changes are not wanted; a failing receiver gets three more tries.
    await ada.patch(f'{base}/tickets/{one["id"]}', json={'priority': 'high'})
    await app.run_jobs()
    assert len(app.websites.to(HOOK)) == 2
    app.websites.answer(HOOK, 500)
    await posted(ada, f'{base}/tickets/{one["id"]}/messages', kind='internal', body='Note')
    await app.run_jobs()
    delays = []
    for _ in range(4):
        delays += await app.run_delayed()
    assert delays == [60, 300, 1800]
    deliveries = (await ada.get(f'{base}/webhooks/{created["id"]}/deliveries')).json()
    assert [(each['attempt'], each['status'], each['error']) for each in deliveries[:4]] == [
        (4, 500, 'HTTP 500'),
        (3, 500, 'HTTP 500'),
        (2, 500, 'HTTP 500'),
        (1, 500, 'HTTP 500'),
    ]
    shown = (await ada.get(f'{base}/webhooks')).json()[0]
    assert (shown['last_status'], shown['last_error']) == (500, 'HTTP 500')

    # A new secret, the test button, unreachable and forbidden addresses.
    changed = await ada.patch(
        f'{base}/webhooks/{created["id"]}',
        json={'name': 'CRM', 'url': HOOK, 'events': ['ticket.changed'], 'new_secret': True},
    )
    assert changed.json()['secret'] not in (None, secret)
    app.websites.fail(HOOK, FetchFailedError('The address did not answer'))
    assert (await ada.post(f'{base}/webhooks/{created["id"]}/test')).status_code == 202
    await app.run_jobs()
    assert (await ada.get(f'{base}/webhooks/{created["id"]}/deliveries')).json()[0][
        'error'
    ] == 'The address did not answer'
    app.websites.fail(HOOK, FetchBlockedError())
    await ada.post(f'{base}/webhooks/{created["id"]}/test')
    await app.run_jobs()
    assert (await ada.get(f'{base}/webhooks/{created["id"]}/deliveries')).json()[0]['error'] == (
        'The address is not on the public internet'
    )

    for body, field in [
        ({'name': 'X', 'url': 'ftp://x.example', 'events': ['ticket.created']}, 'url'),
        ({'name': ' ', 'url': HOOK, 'events': ['ticket.created']}, 'name'),
    ]:
        answer = (await ada.post(f'{base}/webhooks', json=body)).json()
        assert (answer['error'], answer['params']) == ('invalid_webhook', {'field': field})
    assert (await ada.delete(f'{base}/webhooks/{created["id"]}')).status_code == 204
    missing = '0196f3c0-0000-7000-8000-000000000009'
    assert (await ada.delete(f'{base}/webhooks/{missing}')).json()['error'] == 'webhook_not_found'
    assert (await ada.get(f'{base}/webhooks/{missing}/deliveries')).json()['error'] == 'webhook_not_found'
    assert (
        await ada.patch(f'{base}/webhooks/{missing}', json={'name': 'X', 'url': HOOK, 'events': ['ticket.created']})
    ).json()['error'] == 'webhook_not_found'
    agent = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    assert (await agent.get(f'{base}/webhooks')).status_code == 403


async def test_reports_count_tickets_and_times(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    billing = await queue(ada, tenant, 'Billing')
    ada_id = await user_id_of(ada)

    # 22 October 2026, 12:00 UTC: three tickets; one answered after an hour, one closed after two.
    first = await ticket(ada, tenant, support)
    second = await ticket(ada, tenant, billing, 'Invoice', owner_id=ada_id)
    await ticket(ada, tenant, support, 'Call', channel='phone')
    app.clock.advance(hours=1)
    await posted(ada, f'{base}/tickets/{first["id"]}/messages', kind='public', body='On it')
    app.clock.advance(hours=1)
    await ada.patch(f'{base}/tickets/{second["id"]}', json={'state': 'closed'})
    app.clock.advance(days=1)
    await ada.patch(f'{base}/tickets/{second["id"]}', json={'state': 'open'})
    await ada.patch(f'{base}/tickets/{second["id"]}', json={'state': 'closed'})

    report = (await ada.get(f'{base}/reports', params={'start': '2026-10-22', 'end': '2026-10-23'})).json()
    assert (report['created'], report['closed'], report['open_now'], report['unassigned_now']) == (3, 1, 2, 2)
    assert (report['first_response_median'], report['first_response_average']) == (60.0, 60.0)
    # Closed again a day later: from opening to the last close.
    assert report['resolution_median'] == 1560.0
    assert report['reopened'] == 1
    assert report['days'] == [
        {'day': '2026-10-22', 'created': 3, 'closed': 0},
        {'day': '2026-10-23', 'created': 0, 'closed': 1},
    ]
    assert {each['key']: each['open'] for each in report['queues']} == {support: 2, billing: 0}
    assert {each['key'] for each in report['channels']} == {'web', 'phone'}
    assert {each['key'] for each in report['owners']} == {None, ada_id}

    one_queue = (
        await ada.get(
            f'{base}/reports',
            params={'start': '2026-10-22', 'end': '2026-10-22', 'queue_id': billing, 'timezone': 'Europe/Berlin'},
        )
    ).json()
    assert (one_queue['created'], one_queue['closed']) == (1, 0)

    for params, field in [
        ({'start': '2026-10-23', 'end': '2026-10-22'}, 'end'),
        ({'start': '2025-01-01', 'end': '2026-10-22'}, 'start'),
        ({'start': '2026-10-22', 'end': '2026-10-22', 'timezone': 'Mars/Base'}, 'timezone'),
    ]:
        answer = (await ada.get(f'{base}/reports', params=params)).json()
        assert (answer['error'], answer['params']) == ('invalid_period', {'field': field})
    agent = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    assert (await agent.get(f'{base}/reports', params={'start': '2026-10-22', 'end': '2026-10-22'})).status_code == 403


async def test_knowledge_base_and_help_center(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'

    public = await posted(
        ada,
        f'{base}/articles',
        title=' Reset  your password ',
        body='Open the login page and click "Forgot password".',
        category='Account',
        tags=['Login', 'password', 'login'],
        visibility='public',
    )
    assert (public['title'], public['tags'], public['author']) == (
        'Reset your password',
        ['login', 'password'],
        'ada@example.org',
    )
    internal = await posted(ada, f'{base}/articles', title='Refund rules', body='Up to 30 days.', category='Billing')

    library = (await ada.get(f'{base}/articles')).json()
    assert [each['title'] for each in library['articles']] == ['Refund rules', 'Reset your password']
    assert library['categories'] == ['Account', 'Billing']
    assert [each['id'] for each in (await ada.get(f'{base}/articles', params={'q': 'forgot'})).json()['articles']] == [
        public['id']
    ]
    assert [each['id'] for each in (await ada.get(f'{base}/articles', params={'q': 'LOGIN'})).json()['articles']] == [
        public['id']
    ]
    assert [
        each['id'] for each in (await ada.get(f'{base}/articles', params={'category': 'Billing'})).json()['articles']
    ] == [internal['id']]

    # Customers see only the public ones, without logging in.
    help_center = (await app.client.get(f'/api/v1/help/{tenant}')).json()
    assert ([each['id'] for each in help_center['articles']], help_center['categories']) == (
        [public['id']],
        ['Account'],
    )
    assert (await app.client.get(f'/api/v1/help/{tenant}/{public["id"]}')).status_code == 200
    assert (await app.client.get(f'/api/v1/help/{tenant}/{internal["id"]}')).json()['error'] == 'article_not_found'

    changed = await ada.patch(
        f'{base}/articles/{internal["id"]}', json={'title': 'Refunds', 'body': 'Up to 14 days.', 'visibility': 'public'}
    )
    assert (changed.json()['title'], changed.json()['category']) == ('Refunds', '')
    assert (await ada.get(f'{base}/articles/{internal["id"]}')).json()['body'] == 'Up to 14 days.'
    for body, field in [({'title': ' ', 'body': 'x'}, 'title'), ({'title': 'X', 'body': ' '}, 'body')]:
        answer = (await ada.post(f'{base}/articles', json=body)).json()
        assert (answer['error'], answer['params']) == ('invalid_article', {'field': field})
    agent = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    assert len((await agent.get(f'{base}/articles')).json()['articles']) == 2
    assert (await agent.post(f'{base}/articles', json={'title': 'X', 'body': 'Y'})).status_code == 403
    assert (await ada.delete(f'{base}/articles/{internal["id"]}')).status_code == 204
    assert (await ada.delete(f'{base}/articles/{internal["id"]}')).json()['error'] == 'article_not_found'
    assert (await ada.patch(f'{base}/articles/{internal["id"]}', json={'title': 'X', 'body': 'Y'})).json()['error'] == (
        'article_not_found'
    )
