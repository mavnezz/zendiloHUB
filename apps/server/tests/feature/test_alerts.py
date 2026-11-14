import json
from pathlib import Path

from support.app import AppUnderTest, running_app
from support.helpdesk import grant, posted, queue, ticket
from support.identity import logged_in
from support.services import Services
from support.tenancy import TENANTS, create_tenant, member_of, user_id_of
from zendilohub.core.events.integration_events import QueueDeleted
from zendilohub.modules.automation.application.services.alerts import ALERTS_PER_TENANT

WORK = ['view', 'create', 'note', 'reply', 'edit']
SLACK = 'https://hooks.slack.example/services/T1/B1/x'
TEAMS = 'https://prod.workflows.example/teams/hook'


async def test_followers_hear_about_new_and_moved_tickets(app: AppUnderTest) -> None:
    ada = await logged_in(app, 'ada@example.org')
    tenant = await create_tenant(ada)
    base = f'{TENANTS}/{tenant}'
    support = await queue(ada, tenant)
    billing = await queue(ada, tenant, 'Billing')
    bob = await member_of(app, tenant, ada, 'bob@example.org', 'agent')
    cleo = await member_of(app, tenant, ada, 'cleo@example.org', 'agent')
    bob_id, cleo_id = await user_id_of(bob), await user_id_of(cleo)
    team = await grant(ada, tenant, support, [bob_id, cleo_id], WORK)
    await grant(ada, tenant, billing, [bob_id], WORK, name='Billing team')

    assert (await bob.get(f'{base}/notifications/queues')).json() == {'queues': []}
    followed = await bob.put(
        f'{base}/notifications/queues',
        json={'queues': [{'queue_id': support}, {'queue_id': billing, 'mode': 'new'}, {'queue_id': support}]},
    )
    assert sorted(each['queue_id'] for each in followed.json()['queues']) == sorted([support, billing])
    # Only queues one may see.
    refused = await cleo.put(f'{base}/notifications/queues', json={'queues': [{'queue_id': billing}]})
    assert (refused.status_code, refused.json()['error']) == (422, 'invalid_followed_queues')
    await cleo.put(f'{base}/notifications/queues', json={'queues': [{'queue_id': support, 'mode': 'all'}]})
    assert (await cleo.get(f'{base}/notifications/queues')).json() == {'queues': [{'queue_id': support, 'mode': 'all'}]}
    await ada.put(f'{base}/notifications/queues', json={'queues': [{'queue_id': support}]})

    created = await ticket(ada, tenant, support)
    path = f'{base}/tickets/{created["id"]}'
    # Customer replies reach the followers in mode `all` only.
    await posted(ada, f'{path}/messages', kind='public', direction='in', body='Any news?')
    await ada.patch(path, json={'queue_id': billing})

    bobs = [(each['kind'], each['actor']) for each in (await bob.get(f'{base}/notifications')).json()['items']]
    assert bobs == [('moved', 'ada@example.org'), ('created', 'ada@example.org')]
    cleos = [(each['kind'], each['actor']) for each in (await cleo.get(f'{base}/notifications')).json()['items']]
    assert cleos == [('message', 'carl@customer.example'), ('created', 'ada@example.org')]
    # Who makes the ticket does not hear about it.
    assert (await ada.get(f'{base}/notifications')).json()['items'] == []

    # By e-mail for those who want it; a follower who lost the queue hears nothing more.
    await bob.put(f'{base}/me/notification-settings', json={'email': True})
    another = await ticket(cleo, tenant, support, subject='Scanner broken')
    mail = app.mailer.to('bob@example.org')[-1]
    assert mail.subject == f'[#{another["number"]}] Scanner broken: new ticket'
    await ada.put(f'{base}/queue-rights', json={'group_id': team, 'queue_id': support, 'rights': []})
    await ticket(ada, tenant, support, subject='Third')
    newest = (await bob.get(f'{base}/notifications')).json()['items'][0]
    assert newest['subject'] == 'Scanner broken'

    # Leaving the organization forgets the followed queues.
    await ada.delete(f'{base}/members/{cleo_id}')
    async with app.app.context.db.connection() as connection:
        row = await (
            await connection.execute('SELECT count(*) AS n FROM followed_queues WHERE user_id = %s', (cleo_id,))
        ).fetchone()
    assert row is not None
    assert row['n'] == 0


async def test_triggers_send_alerts_by_email(services: Services, template_database: None, tmp_path: Path) -> None:
    async with running_app(services, tmp_path, 'test_alerts_mail', public_url='https://help.example.org') as app:
        ada = await logged_in(app, 'ada@example.org')
        tenant = await create_tenant(ada)
        base = f'{TENANTS}/{tenant}'
        support = await queue(ada, tenant)
        billing = await queue(ada, tenant, 'Billing')
        rule = await posted(
            ada,
            f'{base}/triggers',
            name='Alarm for support',
            event='created',
            conditions=[{'field': 'queue_id', 'operator': 'is', 'value': support}],
            actions={
                'notify_emails': [' Alarm@Example.org ', 'oncall@example.org', 'alarm@example.org'],
                'notify_text': 'Please look at once.',
            },
        )
        assert rule['actions']['notify_emails'] == ['alarm@example.org', 'oncall@example.org']

        created = await ticket(ada, tenant, support, priority='high')
        await ticket(ada, tenant, billing)
        [mail] = app.mailer.to('alarm@example.org')
        assert len(app.mailer.to('oncall@example.org')) == 1
        assert mail.subject == f'[#{created["number"]}] Printer broken'
        assert mail.text.startswith('Please look at once.\n')
        for line in ('Queue: Support', 'Priority: high', 'Customer: carl@customer.example', 'It does not print.'):
            assert line in mail.text
        assert f'https://help.example.org/t/{tenant}/tickets/{created["id"]}' in mail.text
        assert 'Sent by the rule "Alarm for support"' in mail.text

        for kind, body, field in [
            ('macros', {'name': 'M', 'actions': {'notify_emails': ['a@example.org']}}, 'actions.notify_emails'),
            (
                'scheduled-jobs',
                {'name': 'J', 'actions': {'notify_emails': ['a@example.org']}, 'schedule': {'idle_hours': 1}},
                'actions.notify_emails',
            ),
            (
                'triggers',
                {'name': 'T', 'event': 'created', 'actions': {'notify_emails': ['nope']}},
                'actions.notify_emails',
            ),
            ('triggers', {'name': 'T', 'event': 'created', 'actions': {'notify_text': 'x'}}, 'actions.notify_emails'),
            (
                'triggers',
                {
                    'name': 'T',
                    'event': 'created',
                    'actions': {'notify_emails': [f'a{n}@example.org' for n in range(11)]},
                },
                'actions.notify_emails',
            ),
        ]:
            response = await ada.post(f'{base}/{kind}', json=body)
            assert response.status_code == 422, (kind, response.text)
            if response.json().get('error') == 'invalid_rule':
                assert response.json()['params'] == {'field': field}

        # A flood of alerts stops at the limit.
        limiter = app.app.context.rate_limiter
        for _ in range(ALERTS_PER_TENANT.limit):
            await limiter.hit(ALERTS_PER_TENANT, tenant)
        await ticket(ada, tenant, support, subject='Quiet')
        assert len(app.mailer.to('alarm@example.org')) == 1


async def test_slack_and_teams_hear_about_their_queues(
    services: Services, template_database: None, tmp_path: Path
) -> None:
    async with running_app(services, tmp_path, 'test_alerts_chat', public_url='https://help.example.org') as app:
        ada = await logged_in(app, 'ada@example.org')
        tenant = await create_tenant(ada)
        base = f'{TENANTS}/{tenant}'
        support = await queue(ada, tenant)
        billing = await queue(ada, tenant, 'Billing & Co')
        app.websites.answer(SLACK, 200)
        app.websites.answer(TEAMS, 202)

        slack = await posted(
            ada,
            f'{base}/webhooks',
            name='Slack billing',
            url=SLACK,
            events=['ticket.created', 'ticket.changed'],
            format='slack',
            queue_ids=[billing],
        )
        assert (slack['format'], slack['queue_ids']) == ('slack', [billing])
        teams = await posted(
            ada, f'{base}/webhooks', name='Teams', url=TEAMS, events=['ticket.created', 'message.added'], format='teams'
        )
        unknown = await ada.post(
            f'{base}/webhooks',
            json={'name': 'X', 'url': SLACK, 'events': ['ticket.created'], 'queue_ids': [tenant]},
        )
        assert unknown.json()['params'] == {'field': 'queue_ids'}

        not_for_slack = await ticket(ada, tenant, support, subject='Not for Slack')
        billed = await ticket(ada, tenant, billing, subject='<b>Fish & chips</b> [click](https://evil.example)')
        await app.run_jobs()

        [to_slack] = app.websites.to(SLACK)
        message = json.loads(to_slack.body)
        title = f'*New ticket #{billed["number"]} &lt;b&gt;Fish &amp; chips&lt;/b&gt; [click](https://evil.example)*'
        assert message['blocks'][0]['text']['text'] == title
        assert '*Queue:* Billing &amp; Co' in message['blocks'][1]['text']['text']
        link = f'https://help.example.org/t/{tenant}/tickets/{billed["id"]}'
        assert message['blocks'][2]['elements'][0]['url'] == link
        assert message['text'].endswith(f'<{link}|Open ticket #{billed["number"]}>')

        cards = [json.loads(each.body) for each in app.websites.to(TEAMS)]
        assert [each['type'] for each in cards] == ['message', 'message', 'message', 'message']
        card = cards[-1]['attachments'][0]
        assert card['contentType'] == 'application/vnd.microsoft.card.adaptive'
        content = card['content']
        assert content['type'] == 'AdaptiveCard'
        # Brackets cannot make links in the card.
        assert '[click]' not in content['body'][0]['text']
        assert content['actions'] == [
            {'type': 'Action.OpenUrl', 'title': f'Open ticket #{billed["number"]}', 'url': link}
        ]

        # Moving a ticket into the queue is a change Slack hears about; the test button sends a plain notice.
        app.websites.requests.clear()
        await ada.patch(f'{base}/tickets/{not_for_slack["id"]}', json={'queue_id': billing, 'priority': 'high'})
        await ada.post(f'{base}/webhooks/{slack["id"]}/test')
        await app.run_jobs()
        bodies = [json.loads(each.body) for each in app.websites.to(SLACK)]
        assert 'changed' in bodies[0]['blocks'][0]['text']['text']
        assert '*Priority:* normal → high' in bodies[0]['blocks'][1]['text']['text']
        assert bodies[1] == {
            'text': 'Test message from zendiloHUB',
            'blocks': [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': '*Test message from zendiloHUB*'}}],
        }

        # A webhook only for a deleted queue is switched off rather than hearing about all queues.
        await app.app.context.events.publish(QueueDeleted(tenant_id=tenant, queue_id=billing))
        hooks = {each['name']: each for each in (await ada.get(f'{base}/webhooks')).json()}
        assert (hooks['Slack billing']['queue_ids'], hooks['Slack billing']['active']) == ([], False)
        assert hooks['Teams']['active'] is True
        assert teams['format'] == 'teams'
