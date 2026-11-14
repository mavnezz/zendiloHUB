from typing import Any

from support.app import AppUnderTest
from support.helpdesk import posted, queue
from support.mail_desk import SUPPORT, account_body, fetch, mail_desk, tickets
from support.mail_server import email

SALES = 'sales@acme.example'
ALERTS = 'alerts@acme.example'
MISSING = '0196f3c0-0000-7000-8000-000000000009'


def rule(name: str, value: str, **actions: Any) -> dict[str, Any]:
    return {
        'name': name,
        'conditions': [{'field': 'subject', 'operator': 'contains', 'value': value}],
        'actions': actions,
        'stop': True,
    }


async def test_each_mailbox_has_its_rules_and_a_default_queue(app: AppUnderTest) -> None:
    ada, tenant, base, support, account = await mail_desk(app)
    billing = await queue(ada, tenant, 'Billing')
    sales_queue = await queue(ada, tenant, 'Sales')
    sales = await posted(
        ada,
        f'{base}/email-accounts',
        **account_body(sales_queue, name='Sales', address=SALES, imap={'host': 'imap.acme.example', 'port': 993}),
    )
    # For all mailboxes (they run first), and the rules of support@ only.
    spam = await posted(ada, f'{base}/mail-filters', **rule('Spam', 'viagra', ignore=True))
    invoices = await posted(
        ada, f'{base}/mail-filters', **rule('Invoices', 'invoice', queue_id=billing), account_id=account['id']
    )
    urgent = await posted(
        ada, f'{base}/mail-filters', **rule('Urgent', 'urgent', priority='urgent'), account_id=account['id']
    )
    assert (spam['account_id'], invoices['account_id'], invoices['position'], urgent['position']) == (
        None,
        account['id'],
        1,
        2,
    )

    app.mail.deliver(SUPPORT, email(subject='Invoice 42', message_id='<a@x>'))
    app.mail.deliver(SALES, email(to=SALES, subject='Invoice 43', message_id='<b@x>'))
    app.mail.deliver(SUPPORT, email(subject='Printer', message_id='<c@x>'))
    app.mail.deliver(SALES, email(to=SALES, subject='Cheap viagra', message_id='<d@x>'))
    await fetch(app)
    by_subject = {each['subject']: each['queue_id'] for each in await tickets(ada, base)}
    # The rule of support@ moves its invoices; sales@ has no rules: its default queue.
    assert by_subject == {'Invoice 42': billing, 'Invoice 43': sales_queue, 'Printer': support}

    # Each scope has its own order; a filter of another scope cannot join it.
    listed = (await ada.get(f'{base}/mail-filters')).json()
    assert [each['name'] for each in listed] == ['Spam', 'Invoices', 'Urgent']
    reordered = await ada.put(
        f'{base}/mail-filters-order', json={'filter_ids': [urgent['id']], 'account_id': account['id']}
    )
    assert [(each['name'], each['position']) for each in reordered.json()] == [
        ('Spam', 1),
        ('Urgent', 1),
        ('Invoices', 2),
    ]
    foreign = await ada.put(f'{base}/mail-filters-order', json={'filter_ids': [spam['id']], 'account_id': sales['id']})
    assert foreign.json()['error'] == 'filter_not_found'
    # Moved to another scope, a filter goes to its end.
    moved = await ada.patch(
        f'{base}/mail-filters/{invoices["id"]}',
        json=rule('Invoices', 'invoice', queue_id=billing) | {'account_id': sales['id']},
    )
    assert (moved.json()['account_id'], moved.json()['position']) == (sales['id'], 1)
    unknown = (await ada.post(f'{base}/mail-filters', json=rule('X', 'x', tags=['x']) | {'account_id': MISSING})).json()
    assert (unknown['error'], unknown['params']) == ('invalid_filter', {'field': 'account_id'})


async def test_tests_where_an_email_would_go(app: AppUnderTest) -> None:
    ada, tenant, base, support, account = await mail_desk(app)
    billing = await queue(ada, tenant, 'Billing')
    tagged = await posted(
        ada,
        f'{base}/mail-filters',
        name='Tag',
        conditions=[{'field': 'delivered_to', 'operator': 'equals', 'value': 'billing@acme.example'}],
        actions={'tags': ['alias']},
    )
    invoices = await posted(
        ada, f'{base}/mail-filters', **rule('Invoices', 'invoice', queue_id=billing), account_id=account['id']
    )
    raw = email(subject='Invoice 7', Delivered_To='<billing@acme.example>').decode()

    trace = (await ada.post(f'{base}/mail-filters/test', json={'raw': raw, 'account_id': account['id']})).json()
    assert [each['id'] for each in trace['matched']] == [tagged['id'], invoices['id']]
    assert (trace['stopped'], trace['ignore'], trace['tags'], trace['checked']) == (True, False, ['alias'], 2)
    assert (trace['queue_id'], trace['default_queue_id'], trace['final_queue_id']) == (billing, support, billing)

    # Without a mailbox only the filters for all mailboxes run, and there is no default queue.
    trace = (await ada.post(f'{base}/mail-filters/test', json={'raw': raw})).json()
    assert (len(trace['matched']), trace['final_queue_id'], trace['checked']) == (1, None, 1)
    plain = email(subject='Hello').decode()
    trace = (await ada.post(f'{base}/mail-filters/test', json={'raw': plain, 'account_id': account['id']})).json()
    assert (trace['matched'], trace['stopped'], trace['final_queue_id']) == ([], False, support)
    answer = await ada.post(f'{base}/mail-filters/test', json={'raw': plain, 'account_id': MISSING})
    assert answer.json()['error'] == 'account_not_found'


async def test_mailboxes_for_incoming_mail_only(app: AppUnderTest) -> None:
    ada, _tenant, base, support, _account = await mail_desk(app)
    alerts = await posted(
        ada, f'{base}/email-accounts', **account_body(support, name='Alerts', address=ALERTS, smtp=None)
    )
    assert alerts['smtp'] is None
    probe = (await ada.post(f'{base}/email-accounts/{alerts["id"]}/test')).json()
    assert probe == {'imap': None, 'smtp': None}
    # No queue can send with it.
    answer = (await ada.put(f'{base}/queue-channels/{support}', json={'account_id': alerts['id']})).json()
    assert (answer['error'], answer['params']) == ('invalid_queue_settings', {'field': 'account_id'})

    # Its mail lands in its queue; the acknowledgement and the replies go out by the queue's account.
    channel = {
        'account_id': _account['id'],
        'auto_reply': True,
        'auto_reply_subject': 'Got it',
        'auto_reply_body': 'We will answer soon.',
    }
    assert (await ada.put(f'{base}/queue-channels/{support}', json=channel)).status_code == 200
    app.mail.deliver(ALERTS, email(to=ALERTS, subject='Disk full'))
    await fetch(app)
    [ticket] = await tickets(ada, base)
    assert ticket['queue_id'] == support
    assert [(sender, mail.subject) for sender, mail in app.mail.sent] == [(SUPPORT, 'Got it [#1001]')]
    reply = await posted(ada, f'{base}/tickets/{ticket["id"]}/messages', kind='public', body='On it')
    await app.run_jobs()
    assert app.mail.sent[-1][0] == SUPPORT

    # Without the queue's account it cannot fall back to the incoming-only mailbox.
    await ada.put(f'{base}/queue-channels/{support}', json={})
    second = await posted(ada, f'{base}/tickets/{ticket["id"]}/messages', kind='public', body='Again')
    await app.run_jobs()
    statuses = {
        each['message_id']: each for each in (await ada.get(f'{base}/tickets/{ticket["id"]}/deliveries')).json()
    }
    assert (statuses[reply['id']]['status'], statuses[second['id']]['error']) == ('sent', 'no_account')
