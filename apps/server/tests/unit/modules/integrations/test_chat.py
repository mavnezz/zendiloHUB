from typing import Any

from zendilohub.modules.integrations.domain.models.chat import (
    TEXT_MAX,
    chat_body,
    notice,
    slack_escape,
    teams_escape,
)

TICKET = {'number': 7, 'subject': 'Printer <broken>', 'priority': 'high', 'channel': 'email', 'customer_email': None}


def payload(event: str, **data: Any) -> dict[str, Any]:
    return {'event': event, 'data': {'ticket': TICKET, 'queue_name': 'Support', **data}}


def test_escapes_slack_control_characters() -> None:
    assert slack_escape('a & <b> > c') == 'a &amp; &lt;b&gt; &gt; c'


def test_teams_brackets_make_no_links() -> None:
    assert (
        teams_escape('[x](https://evil.example)')
        == '\N{FULLWIDTH LEFT SQUARE BRACKET}x\N{FULLWIDTH RIGHT SQUARE BRACKET}(https://evil.example)'
    )


def test_describes_every_event() -> None:
    created = notice(payload('ticket.created'))
    assert created.title == 'New ticket #7 Printer <broken>'
    assert created.facts == (('Queue', 'Support'), ('Priority', 'high'), ('Channel', 'email'))
    assert created.url is None

    changed = notice(
        payload(
            'ticket.changed',
            changes=[
                {'field': 'state', 'old': 'new', 'new': 'open'},
                {'field': 'owner_id', 'old': None, 'new': 'u1'},
                {'field': 'mystery', 'old': None, 'new': 'x'},
                {'field': 'tags', 'old': None, 'new': None},
            ],
        )
    )
    assert changed.facts == (
        ('State', 'new → open'),
        ('Owner', 'changed'),
        ('mystery', 'changed'),
        ('Tags', 'none → none'),
        ('Queue', 'Support'),
    )
    moved = notice(payload('ticket.changed', changes=[{'field': 'queue_id', 'old': 'a', 'new': 'b'}]))
    assert moved.facts == (('Queue', 'Support'),)

    note = notice(payload('message.added', message={'kind': 'internal', 'direction': 'out'}))
    assert note.title == 'New internal note from the team in #7 Printer <broken>'
    reply = notice(payload('message.added', message={'kind': 'public', 'direction': 'in'}))
    assert reply.title == 'New message from the customer in #7 Printer <broken>'
    breached = notice(payload('sla.breached', kind='first_response'))
    assert breached.facts == (('Queue', 'Support'), ('Target', 'first_response'))
    other = notice(payload('ticket.other'))
    assert other.title == 'ticket.other: #7 Printer <broken>'


def test_cuts_long_texts_and_names_the_customer() -> None:
    long = notice(
        {
            'event': 'ticket.created',
            'data': {'ticket': {**TICKET, 'subject': 'x' * 1000, 'customer_email': 'c@example.org'}},
        }
    )
    assert len(long.title) == len('New ticket #7 ') + TEXT_MAX
    assert ('Customer', 'c@example.org') in long.facts
    # No queue name: the fact is left out.
    assert all(name != 'Queue' for name, _ in long.facts)


def test_builds_slack_and_teams_bodies() -> None:
    event = payload('ticket.created', ticket_url='https://help.example.org/t/x/tickets/y')
    slack = chat_body('slack', event)
    assert slack is not None
    assert slack['blocks'][0]['text']['text'] == '*New ticket #7 Printer &lt;broken&gt;*'
    assert slack['blocks'][2]['elements'][0]['url'] == 'https://help.example.org/t/x/tickets/y'
    teams = chat_body('teams', event)
    assert teams is not None
    content = teams['attachments'][0]['content']
    assert content['body'][1]['facts'][0] == {'title': 'Queue', 'value': 'Support'}
    assert content['actions'][0]['url'] == 'https://help.example.org/t/x/tickets/y'
    assert chat_body('json', event) is None

    ping = chat_body('teams', {'event': 'ticket.created', 'data': {'ping': True}})
    assert ping is not None
    assert 'actions' not in ping['attachments'][0]['content']
    assert len(ping['attachments'][0]['content']['body']) == 1
