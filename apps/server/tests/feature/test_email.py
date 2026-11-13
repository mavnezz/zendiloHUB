from typing import Any

import httpx

from support.app import AppUnderTest
from support.helpdesk import posted, queue
from support.identity import logged_in
from support.mail_server import email
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of

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


async def test_sets_up_email_accounts(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)

    created = await posted(ada, f'{base}/email-accounts', **account_body(support, address=' Support@ACME.example '))
    assert (created['address'], created['imap']['has_password'], created['smtp']['port']) == (SUPPORT, True, 587)
    assert 'password' not in created['imap']
    path = f'{base}/email-accounts/{created["id"]}'

    # Without a password in the request, the stored one stays.
    body = account_body(support, name='Help desk')
    body['imap'].pop('password')
    body['smtp']['password'] = None
    changed = (await ada.patch(path, json=body)).json()
    assert (changed['name'], changed['imap']['has_password']) == ('Help desk', True)
    assert (await ada.post(f'{path}/test')).json() == {'imap': None, 'smtp': None}
    app.mail.passwords[SUPPORT] = 'right'
    probe = (await ada.post(f'{path}/test')).json()
    assert probe['imap'] == 'The server said: [AUTHENTICATIONFAILED] Invalid credentials'
    assert (await ada.post(f'{path}/fetch')).status_code == 202
    assert app.jobs.enqueued[-1] == ('channels.fetch', (tenant, created['id']))

    taken = await ada.post(f'{base}/email-accounts', json=account_body(support))
    assert taken.json()['error'] == 'account_address_taken'
    for field, value in [('address', 'nope'), ('name', ' ')]:
        refused = (await ada.post(f'{base}/email-accounts', json=account_body(support, **{field: value}))).json()
        assert (refused['error'], refused['params']) == ('invalid_account', {'field': field})
    bad_host = account_body(support, address='x@acme.example')
    bad_host['imap']['host'] = 'bad host'
    assert (await ada.post(f'{base}/email-accounts', json=bad_host)).json()['params'] == {'field': 'imap.host'}
    long_password = account_body(support, address='y@acme.example')
    long_password['smtp']['password'] = 'x' * 1000 + 'y'
    assert (await ada.post(f'{base}/email-accounts', json=long_password)).status_code == 422

    assert [each['name'] for each in (await ada.get(f'{base}/email-accounts')).json()] == ['Help desk']
    assert (await ada.delete(path)).status_code == 204
    missing = (await ada.delete(path)).json()
    assert missing['error'] == 'account_not_found'
    assert (await ada.patch(path, json=account_body(support))).json()['error'] == 'account_not_found'
    assert (await ada.post(f'{path}/test')).json()['error'] == 'account_not_found'

    agent = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    assert (await agent.get(f'{base}/email-accounts')).status_code == 403
    log = {entry['action'] for entry in (await ada.get(f'{base}/audit-log')).json()['items']}
    assert {'email_account.created', 'email_account.updated', 'email_account.deleted'} <= log


async def test_mails_become_tickets_and_answers_join_them(app: AppUnderTest) -> None:
    ada, _tenant, base, support, _account = await mail_desk(app)
    await ada.put(
        f'{base}/queue-channels/{support}',
        json={
            'account_id': _account['id'],
            'auto_reply': True,
            'auto_reply_subject': 'We got your message: {{ticket.subject}}',
            'auto_reply_body': 'Hello {{customer.name}},\nyour ticket is #{{ticket.number}} at {{organization.name}}.',
        },
    )
    app.mail.deliver(SUPPORT, email(html='<p>It does <b>not</b> print.</p><script>alert(1)</script>'))

    await fetch(app)

    [created] = await tickets(ada, base)
    assert (created['number'], created['subject'], created['channel'], created['queue_id'], created['state']) == (
        1001,
        'Printer broken',
        'email',
        support,
        'new',
    )
    assert (created['customer']['email'], created['customer']['name']) == ('carl@customer.example', 'Carl Customer')
    [message] = (await ada.get(f'{base}/tickets/{created["id"]}/messages')).json()
    assert (message['from_address'], message['author_name'], message['direction']) == (
        'carl@customer.example',
        'Carl Customer',
        'in',
    )
    assert message['body'] == 'It does not print.'
    assert message['body_html'] == '<p>It does <b>not</b> print.</p>'

    # The queue's auto reply went out, marked as automatic so robots do not answer it.
    [(sender, reply)] = app.mail.sent
    assert (sender, reply.sender, reply.to) == (
        SUPPORT,
        'Acme Support <support@acme.example>',
        ('carl@customer.example',),
    )
    assert reply.subject == 'We got your message: Printer broken [#1001]'
    assert reply.text == 'Hello Carl Customer,\nyour ticket is #1001 at Acme GmbH.'
    assert (reply.automatic, reply.in_reply_to) == (True, '<m1@customer.example>')

    # An answer to the mail joins the ticket; so does one with the number in its subject only.
    app.mail.deliver(
        SUPPORT,
        email(subject='Re: Printer broken', message_id='<m2@customer.example>', In_Reply_To='<m1@customer.example>'),
    )
    app.mail.deliver(SUPPORT, email(subject='Any news? [#1001]', message_id='<m3@customer.example>'))
    # Fetched again: nothing twice.
    app.mail.deliver(SUPPORT, email(message_id='<m3@customer.example>', subject='Copy'))
    await fetch(app)
    await fetch(app)

    assert len(await tickets(ada, base)) == 1
    assert len((await ada.get(f'{base}/tickets/{created["id"]}/messages')).json()) == 3
    assert len(app.mail.sent) == 1


async def test_robots_and_own_mails_get_no_reply(app: AppUnderTest) -> None:
    ada, _tenant, base, support, account = await mail_desk(app)
    await ada.put(
        f'{base}/queue-channels/{support}',
        json={
            'account_id': account['id'],
            'auto_reply': True,
            'auto_reply_subject': 'Got it',
            'auto_reply_body': 'Thanks',
        },
    )
    app.mail.deliver(SUPPORT, email(sender='robot@vendor.example', message_id='<r1@x>', Auto_Submitted='auto-replied'))
    app.mail.deliver(SUPPORT, email(sender='news@vendor.example', message_id='<r2@x>', Precedence='bulk'))
    app.mail.deliver(SUPPORT, email(sender=SUPPORT, message_id='<own@x>'))
    for index in range(4):
        app.mail.deliver(
            SUPPORT, email(sender='busy@customer.example', message_id=f'<b{index}@x>', subject=f'#{index}')
        )

    await fetch(app)

    # Robots open tickets, but get no auto reply; our own address opens none; nobody gets more than three an hour.
    assert len(await tickets(ada, base)) == 6
    assert [mail.to for _, mail in app.mail.sent] == [('busy@customer.example',)] * 3


async def test_replies_go_out_by_email_in_the_thread(app: AppUnderTest) -> None:
    ada, tenant, base, support, account = await mail_desk(app)
    app.mail.deliver(SUPPORT, email())
    await fetch(app)
    [ticket] = await tickets(ada, base)
    path = f'{base}/tickets/{ticket["id"]}'

    reply = await posted(ada, f'{path}/messages', kind='public', body='Please restart it.')
    await posted(ada, f'{path}/messages', kind='internal', body='Not for the customer')
    await app.run_jobs()

    [(sender, sent)] = app.mail.sent
    assert (sender, sent.subject, sent.text) == (SUPPORT, 'Re: Printer broken [#1001]', 'Please restart it.')
    assert (sent.in_reply_to, sent.references) == ('<m1@customer.example>', ('<m1@customer.example>',))
    deliveries = (await ada.get(f'{path}/deliveries')).json()
    assert [(each['message_id'], each['status']) for each in deliveries] == [(reply['id'], 'sent')]
    messages = (await ada.get(f'{path}/messages')).json()
    assert messages[1]['from_address'] == SUPPORT

    # The customer answers our mail: it finds the ticket by our Message-ID.
    app.mail.deliver(SUPPORT, email(subject='Re: Re: Printer broken', message_id='<m9@c>', In_Reply_To=sent.message_id))
    await fetch(app)
    assert len((await ada.get(f'{path}/messages')).json()) == 4

    # A broken SMTP server: tried again later, then given up; a click sends it again.
    app.mail.broken[SUPPORT] = 'The server did not answer'
    second = await posted(ada, f'{path}/messages', kind='public', body='Second try')
    await app.run_jobs()
    delays = []
    for _ in range(5):
        delays += await app.run_delayed()
    assert delays == [60, 300, 900, 3600]
    failed = {each['message_id']: each for each in (await ada.get(f'{path}/deliveries')).json()}[second['id']]
    assert (failed['status'], failed['error'], failed['attempts']) == ('failed', 'The server did not answer', 5)
    del app.mail.broken[SUPPORT]
    assert (await ada.post(f'{path}/deliveries/{second["id"]}/resend')).status_code == 202
    await app.run_jobs()
    assert [mail.text for _, mail in app.mail.sent][-1] == 'Second try'

    # Without an account for the queue (or an address of the customer), replies stay in the ticket.
    await ada.put(f'{base}/queue-channels/{support}', json={})
    third = await posted(ada, f'{path}/messages', kind='public', body='Third')
    await app.run_jobs()
    phone = await posted(
        ada, f'{base}/tickets', queue_id=support, subject='Call', body='Called', customer={'phone': '+49 30 1'}
    )
    await ada.put(f'{base}/queue-channels/{support}', json={'account_id': account['id']})
    fourth = await posted(ada, f'{base}/tickets/{phone["id"]}/messages', kind='public', body='Fourth')
    await app.run_jobs()
    statuses = {each['message_id']: each for each in (await ada.get(f'{path}/deliveries')).json()}
    assert (statuses[third['id']]['status'], statuses[third['id']]['error']) == ('skipped', 'no_account')
    phone_status = (await ada.get(f'{base}/tickets/{phone["id"]}/deliveries')).json()
    assert [(each['message_id'], each['error']) for each in phone_status] == [(fourth['id'], 'no_customer_address')]
    assert tenant


async def test_signatures_salutations_and_the_reply_draft(app: AppUnderTest) -> None:
    ada, tenant, base, support, account = await mail_desk(app)
    signature = await posted(
        ada,
        f'{base}/text-templates',
        kind='signature',
        name='Standard',
        body='Best regards\n{{agent.name}}\n{{agent.title}}\n{{agent.signature}}\n{{organization.name}} · {{queue.name}}',
    )
    salutation = await posted(
        ada, f'{base}/text-templates', kind='salutation', name='Hello', body='Hello {{customer.name}},'
    )
    refused = (
        await ada.post(f'{base}/text-templates', json={'kind': 'signature', 'name': 'X', 'body': '{{agent.age}}'})
    ).json()
    assert (refused['error'], refused['params']) == ('invalid_template', {'field': 'body', 'placeholder': 'agent.age'})
    listed = (await ada.get(f'{base}/text-templates')).json()
    assert [each['name'] for each in listed['templates']] == ['Hello', 'Standard']
    assert 'ticket.number' in listed['placeholders']

    settings = await ada.put(
        f'{base}/queue-channels/{support}',
        json={'account_id': account['id'], 'signature_id': signature['id'], 'salutation_id': salutation['id']},
    )
    assert settings.json()['signature_id'] == signature['id']
    personal = await ada.put(
        f'{base}/me/email-settings', json={'name': 'Ada Lovelace', 'title': 'Support', 'signature': 'Tel. 123'}
    )
    assert personal.json()['name'] == 'Ada Lovelace'
    assert (await ada.get(f'{base}/me/email-settings')).json()['signature'] == 'Tel. 123'

    draft = await ada.get(
        f'{base}/queues/{support}/reply-draft', params={'customer_name': 'Carl', 'number': 1001, 'subject': 'Printer'}
    )
    assert draft.json()['text'] == (
        'Hello Carl,\n\n\n\nBest regards\nAda Lovelace\nSupport\nTel. 123\nAcme GmbH · Support'
    )

    # Bob has no personal settings: his name comes from his address, and empty lines go.
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    draft = (await bob.get(f'{base}/queues/{support}/reply-draft')).json()['text']
    assert draft == 'Hello ,\n\n\n\nBest regards\nbob\nAcme GmbH · Support'
    billing = await queue(ada, tenant, 'Billing')
    assert (await bob.get(f'{base}/queues/{billing}/reply-draft')).json()['text'] == ''
    await ada.put(f'{base}/queue-channels/{billing}', json={'salutation_id': salutation['id']})
    assert (await bob.get(f'{base}/queues/{billing}/reply-draft')).json()['text'] == 'Hello ,\n\n'

    in_use = (await ada.delete(f'{base}/text-templates/{signature["id"]}')).json()
    assert in_use['error'] == 'template_in_use'
    renamed = await ada.patch(
        f'{base}/text-templates/{signature["id"]}', json={'kind': 'signature', 'name': 'Short', 'body': 'Bye'}
    )
    assert renamed.json()['name'] == 'Short'
    wrong_kind = await ada.patch(
        f'{base}/text-templates/{signature["id"]}', json={'kind': 'salutation', 'name': 'X', 'body': 'Y'}
    )
    assert wrong_kind.json()['error'] == 'template_not_found'
    await ada.put(f'{base}/queue-channels/{support}', json={'account_id': account['id']})
    assert (await ada.delete(f'{base}/text-templates/{signature["id"]}')).status_code == 204
    assert (await ada.delete(f'{base}/text-templates/{signature["id"]}')).json()['error'] == 'template_not_found'

    missing = '0196f3c0-0000-7000-8000-000000000009'
    for body, error in [
        ({'account_id': missing}, 'account_not_found'),
        ({'signature_id': salutation['id']}, 'template_not_found'),
        ({'auto_reply': True}, 'invalid_template'),
        ({'auto_reply_body': '{{nope}}'}, 'invalid_template'),
    ]:
        assert (await ada.put(f'{base}/queue-channels/{support}', json=body)).json()['error'] == error
    assert (await ada.put(f'{base}/queue-channels/{missing}', json={})).json()['error'] == 'invalid_queue_settings'
    assert {each['queue_id'] for each in (await ada.get(f'{base}/queue-channels')).json()} == {support, billing}
    bad_personal = await ada.put(f'{base}/me/email-settings', json={'signature': '{{agent.name}}'})
    assert bad_personal.json()['error'] == 'invalid_template'


async def test_filters_route_and_drop_mails(app: AppUnderTest) -> None:
    ada, tenant, base, _support, _account = await mail_desk(app)
    billing = await queue(ada, tenant, 'Billing')
    invoices = await posted(
        ada,
        f'{base}/mail-filters',
        name='Invoices',
        conditions=[{'field': 'subject', 'operator': 'contains', 'value': 'invoice'}],
        actions={'queue_id': billing, 'priority': 'high', 'tags': ['billing']},
    )
    spam = await posted(
        ada,
        f'{base}/mail-filters',
        name='Spam',
        match='any',
        conditions=[
            {'field': 'header', 'header': 'X-Spam-Flag', 'operator': 'equals', 'value': 'yes'},
            {'field': 'from', 'operator': 'regex', 'value': r'@spam\.example$'},
        ],
        actions={'ignore': True},
    )
    assert [each['position'] for each in (await ada.get(f'{base}/mail-filters')).json()] == [1, 2]
    reordered = (await ada.put(f'{base}/mail-filters-order', json={'filter_ids': [spam['id']]})).json()
    assert [each['name'] for each in reordered] == ['Spam', 'Invoices']

    app.mail.deliver(SUPPORT, email(subject='Your Invoice 42', message_id='<i@x>'))
    app.mail.deliver(SUPPORT, email(sender='x@spam.example', message_id='<s1@x>'))
    app.mail.deliver(SUPPORT, email(message_id='<s2@x>', X_Spam_Flag='YES'))
    await fetch(app)

    [ticket] = await tickets(ada, base)
    assert (ticket['queue_id'], ticket['priority'], ticket['tags']) == (billing, 'high', ['billing'])

    changed = await ada.patch(
        f'{base}/mail-filters/{invoices["id"]}',
        json={
            'name': 'Invoices',
            'active': False,
            'conditions': [{'field': 'body', 'operator': 'not_contains', 'value': 'x'}],
            'actions': {'tags': ['a']},
            'stop': True,
        },
    )
    assert (changed.json()['active'], changed.json()['stop']) == (False, True)
    cases: list[tuple[dict[str, Any], str]] = [
        ({'conditions': [{'field': 'subject', 'operator': 'regex', 'value': '('}]}, 'conditions.value'),
        (
            {'conditions': [{'field': 'header', 'operator': 'equals', 'value': 'x', 'header': 'Bad Header'}]},
            'conditions.header',
        ),
        ({'actions': {}}, 'actions'),
        ({'actions': {'queue_id': '0196f3c0-0000-7000-8000-000000000009'}}, 'actions.queue_id'),
        ({'name': ' '}, 'name'),
    ]
    for body, field in cases:
        request: dict[str, Any] = {
            'name': 'Bad',
            'conditions': [{'field': 'to', 'operator': 'starts_with', 'value': 'x'}],
            'actions': {'tags': ['x']},
            **body,
        }
        answer = (await ada.post(f'{base}/mail-filters', json=request)).json()
        assert (answer['error'], answer['params']) == ('invalid_filter', {'field': field})
    missing = '0196f3c0-0000-7000-8000-000000000009'
    assert (await ada.put(f'{base}/mail-filters-order', json={'filter_ids': [missing]})).json()[
        'error'
    ] == 'filter_not_found'
    assert (await ada.delete(f'{base}/mail-filters/{spam["id"]}')).status_code == 204
    assert (await ada.delete(f'{base}/mail-filters/{spam["id"]}')).json()['error'] == 'filter_not_found'
    request = {
        'name': 'X',
        'conditions': [{'field': 'cc', 'operator': 'ends_with', 'value': 'x'}],
        'actions': {'tags': ['x']},
    }
    assert (await ada.patch(f'{base}/mail-filters/{missing}', json=request)).json()['error'] == 'filter_not_found'


async def test_keeps_mails_that_fail_and_shows_broken_accounts(app: AppUnderTest) -> None:
    ada, _tenant, base, _support, account = await mail_desk(app)
    app.mail.deliver(SUPPORT, b'Subject: No sender\r\n\r\nWho wrote this?')
    await fetch(app)

    [failed] = (await ada.get(f'{base}/failed-emails')).json()
    assert (failed['subject'], failed['error']) == ('No sender', 'ValueError: The e-mail has no sender')
    retried = (await ada.post(f'{base}/failed-emails/{failed["id"]}/retry')).json()
    assert retried == {'outcome': 'failed'}
    [again] = (await ada.get(f'{base}/failed-emails')).json()
    assert (await ada.delete(f'{base}/failed-emails/{again["id"]}')).status_code == 204
    assert (await ada.get(f'{base}/failed-emails')).json() == []
    assert (await ada.delete(f'{base}/failed-emails/{again["id"]}')).json()['error'] == 'failed_email_not_found'
    assert (await ada.post(f'{base}/failed-emails/{again["id"]}/retry')).json()['error'] == 'failed_email_not_found'

    app.mail.broken[SUPPORT] = 'The server name is unknown'
    await fetch(app)
    app.clock.advance(minutes=5)
    await fetch(app)
    [shown] = (await ada.get(f'{base}/email-accounts')).json()
    assert (shown['last_error'], shown['failing_since']) == ('The server name is unknown', '2026-10-22T12:00:00Z')
    del app.mail.broken[SUPPORT]
    await fetch(app)
    [shown] = (await ada.get(f'{base}/email-accounts')).json()
    assert (shown['last_error'], shown['failing_since']) == (None, None)

    # Inactive accounts are not fetched.
    body = account_body(account['queue_id'], active=False)
    await ada.patch(f'{base}/email-accounts/{account["id"]}', json=body)
    app.mail.deliver(SUPPORT, email(message_id='<late@x>'))
    await fetch(app)
    assert await tickets(ada, base) == []


async def test_email_data_goes_with_the_organization_and_its_people(app: AppUnderTest) -> None:
    ada, tenant, base, _support, _account = await mail_desk(app)
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    await bob.put(f'{base}/me/email-settings', json={'name': 'Bob'})
    await ada.delete(f'{base}/members/{await user_id_of(bob)}')

    assert (await ada.delete(base)).status_code == 204

    async with app.app.context.db.connection() as connection:
        for table in ('email_accounts', 'personal_settings', 'queue_channels'):
            row = await (await connection.execute(f'SELECT count(*) AS n FROM {table}'.encode())).fetchone()
            assert row is not None
            assert row['n'] == 0, table
