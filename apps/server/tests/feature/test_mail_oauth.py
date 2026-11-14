from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from support.app import AppUnderTest
from support.helpdesk import posted, queue
from support.identity import logged_in
from support.mail_server import email
from support.tenancy import TENANTS, create_tenant, member_of

SUPPORT = 'support@acme.example'
CALLBACK = '/api/v1/email-oauth/callback'


async def desk(app: AppUnderTest) -> tuple[httpx.AsyncClient, str, str, str]:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    return ada, tenant, f'{TENANTS}/{tenant}', await queue(ada, tenant)


async def start(client: httpx.AsyncClient, base: str, **body: Any) -> str:
    """The state the provider would send back."""
    answer = await posted(client, f'{base}/email-accounts/oauth', 200, **body)
    return str(parse_qs(urlsplit(answer['url']).query)['state'][0])


async def back(client: httpx.AsyncClient, **query: str) -> dict[str, list[str]]:
    """The browser returns from the provider; the query of where the app sends it on."""
    answer = await client.get(CALLBACK, params=query)
    assert answer.status_code == 303, answer.text
    location = urlsplit(answer.headers['location'])
    return {'path': [location.path], **parse_qs(location.query)}


async def connect(app: AppUnderTest, client: httpx.AsyncClient, base: str, **body: Any) -> dict[str, Any]:
    state = await start(client, base, **body)
    landed = await back(client, state=state, code='the-code')
    assert 'connected' in landed, landed
    accounts = (await client.get(f'{base}/email-accounts')).json()
    return next(each for each in accounts if each['id'] == landed['connected'][0])


async def fetch(app: AppUnderTest) -> None:
    await app.app.context.scheduler.run_all()
    await app.run_jobs()


async def test_connects_a_mailbox_with_oauth(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    assert (await ada.get(f'{base}/email-accounts/oauth-providers')).json() == {'providers': ['google', 'microsoft']}

    state = await start(ada, base, provider='google', queue_id=support, name='Gmail', display_name='Acme Support')
    assert state.startswith(f'{tenant}.')
    landed = await back(ada, state=state, code='the-code')
    assert landed['path'] == [f'/t/{tenant}/email-accounts']
    account_id = landed['connected'][0]

    provider, code, verifier, redirect_uri = app.oauth.exchanged[0]
    assert (provider, code, redirect_uri) == ('google', 'the-code', f'http://zendilohub.test{CALLBACK}')
    assert len(verifier) >= 43
    account = (await ada.get(f'{base}/email-accounts')).json()[0]
    assert account['id'] == account_id
    assert (account['name'], account['address'], account['provider'], account['needs_reconnect']) == (
        'Gmail',
        SUPPORT,
        'google',
        False,
    )
    assert (account['imap']['host'], account['imap']['port'], account['imap']['username']) == (
        'imap.gmail.com',
        993,
        SUPPORT,
    )
    assert (account['smtp']['host'], account['smtp']['security'], account['smtp']['has_password']) == (
        'smtp.gmail.com',
        'starttls',
        False,
    )

    # Its address and servers stay the provider's; the rest can change.
    body = {
        'name': 'Help',
        'address': 'other@acme.example',
        'display_name': '',
        'queue_id': support,
        'imap': {'host': 'evil.example', 'port': 143, 'security': 'none', 'username': 'x', 'password': 'pw'},
        'smtp': {'host': 'evil.example', 'port': 25, 'security': 'none', 'username': 'x'},
    }
    changed = (await ada.patch(f'{base}/email-accounts/{account_id}', json=body)).json()
    assert (changed['name'], changed['address'], changed['imap']['host']) == ('Help', SUPPORT, 'imap.gmail.com')
    assert changed['imap']['has_password'] is False

    # The audit log names the mailbox.
    log = (await ada.get(f'{base}/audit-log')).json()['items']
    assert any(each['action'] == 'email_account.connected' and each['target'] == SUPPORT for each in log)


async def test_fetches_and_sends_with_fresh_tokens(app: AppUnderTest) -> None:
    ada, _tenant, base, support = await desk(app)
    account = await connect(app, ada, base, provider='microsoft', queue_id=support)
    assert (account['name'], account['imap']['host']) == (SUPPORT, 'outlook.office365.com')
    path = f'{base}/email-accounts/{account["id"]}'

    app.mail.tokens[SUPPORT] = 'access-1'
    app.mail.deliver(SUPPORT, email())
    await fetch(app)
    tickets = (await ada.get(f'{base}/tickets', params={'view': 'all'})).json()['items']
    assert [each['subject'] for each in tickets] == ['Printer broken']
    assert app.mail.logins[-1][1].oauth
    assert app.mail.logins[-1][1].secret == 'access-1'
    assert app.oauth.refreshed == []

    # Shortly before it runs out the access token is renewed; the provider's new refresh token replaces the old.
    app.clock.advance(minutes=59, seconds=30)
    app.mail.tokens[SUPPORT] = 'access-2'
    assert (await ada.post(f'{path}/test')).json() == {'imap': None, 'smtp': None}
    assert app.oauth.refreshed == [('microsoft', 'refresh-1')]
    app.clock.advance(hours=1)
    app.oauth.rotate = False
    app.mail.tokens[SUPPORT] = 'access-3'
    await fetch(app)
    app.clock.advance(hours=1)
    app.mail.tokens[SUPPORT] = 'access-4'
    await fetch(app)
    assert app.oauth.refreshed[1:] == [('microsoft', 'refresh-2'), ('microsoft', 'refresh-2')]
    assert (await ada.get(f'{base}/email-accounts')).json()[0]['last_error'] is None

    # Replies go out with the token as well.
    answer = await ada.put(f'{base}/queue-channels/{support}', json={'account_id': account['id']})
    assert answer.status_code == 200, answer.text
    ticket = tickets[0]['id']
    reply = await ada.post(f'{base}/tickets/{ticket}/messages', json={'kind': 'public', 'body': 'Restart it.'})
    assert reply.status_code == 201, reply.text
    await app.run_jobs()
    assert [mail.text for _address, mail in app.mail.sent][-1].startswith('Restart it.')
    assert app.mail.logins[-1][1].secret == 'access-4'

    # A provider error that may pass is reported, and tried again next time.
    app.clock.advance(hours=1)
    app.oauth.refresh_error = 'temporarily_unavailable'
    await fetch(app)
    listed = (await ada.get(f'{base}/email-accounts')).json()[0]
    assert (listed['needs_reconnect'], listed['last_error']) == (
        False,
        'The provider could not renew the access (temporarily_unavailable)',
    )


async def test_asks_to_reconnect_when_the_provider_ends_the_connection(app: AppUnderTest) -> None:
    ada, _tenant, base, support = await desk(app)
    account = await connect(app, ada, base, provider='google', queue_id=support)
    path = f'{base}/email-accounts/{account["id"]}'
    app.clock.advance(hours=2)
    app.oauth.refresh_error = 'invalid_grant'
    await fetch(app)
    listed = (await ada.get(f'{base}/email-accounts')).json()[0]
    assert (listed['needs_reconnect'], listed['last_error']) == (
        True,
        'The provider ended the connection (invalid_grant)',
    )
    # Nothing is asked of the provider until it is connected again.
    asked = len(app.oauth.refreshed)
    probe = (await ada.post(f'{path}/test')).json()
    assert probe == {'imap': 'The mailbox must be connected again', 'smtp': 'The mailbox must be connected again'}
    assert len(app.oauth.refreshed) == asked

    app.oauth.refresh_error = None
    again = await connect(app, ada, base, provider='google', account_id=account['id'])
    assert (again['id'], again['needs_reconnect'], again['last_error']) == (account['id'], False, None)
    assert (await ada.post(f'{path}/test')).json() == {'imap': None, 'smtp': None}
    assert len(app.oauth.refreshed) == asked


async def test_switches_a_password_account_to_oauth(app: AppUnderTest) -> None:
    ada, _tenant, base, support = await desk(app)
    server = {'port': 993, 'security': 'ssl', 'username': SUPPORT, 'password': 'pw'}
    created = await posted(
        ada,
        f'{base}/email-accounts',
        name='Support',
        address=SUPPORT,
        queue_id=support,
        imap={'host': 'imap.acme.example', **server},
        smtp={'host': 'smtp.acme.example', **server},
    )
    assert created['imap']['has_password'] is True
    app.oauth.address = 'Support@Acme.example'
    switched = await connect(app, ada, base, provider='microsoft', account_id=created['id'])
    assert (switched['provider'], switched['address'], switched['imap']['has_password']) == (
        'microsoft',
        SUPPORT,
        False,
    )
    assert switched['smtp']['host'] == 'smtp.office365.com'


async def test_refuses_what_did_not_come_from_here(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    page = f'/t/{tenant}/email-accounts'

    # Used once only, and within ten minutes.
    state = await start(ada, base, provider='google', queue_id=support)
    assert 'connected' in await back(ada, state=state, code='c')
    assert await back(ada, state=state, code='c') == {'path': [page], 'oauth_error': ['expired']}
    late = await start(ada, base, provider='google', queue_id=support)
    app.clock.advance(minutes=11)
    assert (await back(ada, state=late, code='c'))['oauth_error'] == ['expired']
    assert await back(ada, state='nonsense', code='c') == {'path': ['/'], 'oauth_error': ['expired']}

    # Only who started it may finish it.
    other = await start(ada, base, provider='google', queue_id=support)
    async with app.new_client() as stranger:
        assert (await back(stranger, state=other, code='c'))['oauth_error'] == ['session']

    # The provider's refusals and errors.
    denied = await start(ada, base, provider='google', queue_id=support)
    assert (await back(ada, state=denied, error='access_denied'))['oauth_error'] == ['denied']
    broken = await start(ada, base, provider='google', queue_id=support)
    app.oauth.exchange_error = 'invalid_grant'
    assert (await back(ada, state=broken, code='c'))['oauth_error'] == ['invalid_grant']
    app.oauth.exchange_error = None
    app.oauth.address = 'not an address'
    nameless = await start(ada, base, provider='google', queue_id=support)
    assert (await back(ada, state=nameless, code='c'))['oauth_error'] == ['no_address']
    app.oauth.address = SUPPORT

    # One account per address.
    twice = await start(ada, base, provider='microsoft', queue_id=support)
    assert (await back(ada, state=twice, code='c'))['oauth_error'] == ['address_taken']
    assert len((await ada.get(f'{base}/email-accounts')).json()) == 1


async def test_checks_what_starts_a_connection(app: AppUnderTest) -> None:
    ada, tenant, base, support = await desk(app)
    app.oauth.providers = ('google',)
    unavailable = await ada.post(f'{base}/email-accounts/oauth', json={'provider': 'microsoft', 'queue_id': support})
    assert (unavailable.status_code, unavailable.json()['error']) == (422, 'oauth_unavailable')
    no_queue = await ada.post(f'{base}/email-accounts/oauth', json={'provider': 'google'})
    assert no_queue.json()['params'] == {'field': 'queue_id'}
    missing = await ada.post(
        f'{base}/email-accounts/oauth',
        json={'provider': 'google', 'account_id': '00000000-0000-7000-8000-00000000ffff'},
    )
    assert missing.json()['error'] == 'account_not_found'

    # E-mail settings are for those who manage them.
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    refused = await bob.post(f'{base}/email-accounts/oauth', json={'provider': 'google', 'queue_id': support})
    assert refused.status_code == 403
