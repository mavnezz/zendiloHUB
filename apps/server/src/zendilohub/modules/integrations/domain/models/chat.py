"""Events as chat messages: a Slack incoming webhook's message or a Microsoft Teams Adaptive Card."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .webhook import WebhookFormat

TEXT_MAX = 300
"""Longer subjects and values are cut, so a message stays a notice."""

KIND_LABELS = {'public': 'message', 'internal': 'internal note'}
FIELD_LABELS = {
    'state': 'State',
    'priority': 'Priority',
    'queue_id': 'Queue',
    'owner_id': 'Owner',
    'responsible_id': 'Responsible',
    'subject': 'Subject',
    'tags': 'Tags',
}


@dataclass(frozen=True, kw_only=True)
class ChatNotice:
    """What a chat message says, before it takes the shape of one chat."""

    title: str
    facts: tuple[tuple[str, str], ...]
    url: str | None
    button: str


def _cut(text: object) -> str:
    plain = ' '.join(str(text).split())
    return plain if len(plain) <= TEXT_MAX else plain[: TEXT_MAX - 1] + '…'


def notice(payload: Mapping[str, Any]) -> ChatNotice:
    """The notice of an event as `AnnounceHandler` builds it (see the JSON format of webhooks)."""
    event = str(payload.get('event', ''))
    data: Mapping[str, Any] = payload.get('data') or {}
    ticket: Mapping[str, Any] | None = data.get('ticket')
    url = data.get('ticket_url') or None
    if data.get('ping') or ticket is None:
        return ChatNotice(title='Test message from zendiloHUB', facts=(), url=None, button='Open ticket')
    label = f'#{ticket.get("number")} {_cut(ticket.get("subject", ""))}'
    queue = _cut(data.get('queue_name') or '')
    facts: list[tuple[str, str]] = []
    if event == 'ticket.created':
        title = f'New ticket {label}'
        facts += [
            ('Queue', queue),
            ('Priority', _cut(ticket.get('priority', ''))),
            ('Channel', _cut(ticket.get('channel', ''))),
        ]
        if ticket.get('customer_email'):
            facts.append(('Customer', _cut(ticket['customer_email'])))
    elif event == 'ticket.changed':
        title = f'Ticket {label} changed'
        for change in data.get('changes') or []:
            field = str(change.get('field', ''))
            if field == 'queue_id':
                facts.append(('Queue', queue))
            elif field in ('state', 'priority', 'subject', 'tags'):
                facts.append(
                    (FIELD_LABELS[field], f'{_cut(change.get("old") or "none")} → {_cut(change.get("new") or "none")}')
                )
            else:
                facts.append((FIELD_LABELS.get(field, _cut(field)), 'changed'))
        if not any(name == 'Queue' for name, _ in facts):
            facts.append(('Queue', queue))
    elif event == 'message.added':
        message: Mapping[str, Any] = data.get('message') or {}
        kind = KIND_LABELS.get(str(message.get('kind')), 'message')
        who = 'the customer' if message.get('direction') == 'in' else 'the team'
        title = f'New {kind} from {who} in {label}'
        facts.append(('Queue', queue))
    elif event == 'sla.breached':
        title = f'Service level missed in {label}'
        facts += [('Queue', queue), ('Target', _cut(data.get('kind') or ''))]
    else:
        title = f'{_cut(event)}: {label}'
    return ChatNotice(
        title=title,
        facts=tuple((name, value) for name, value in facts if value),
        url=url,
        button=f'Open ticket #{ticket.get("number")}',
    )


def slack_escape(text: str) -> str:
    """Slack's mrkdwn: `&`, `<` and `>` are control characters."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def slack_message(item: ChatNotice) -> dict[str, Any]:
    title = slack_escape(item.title)
    lines = '\n'.join(f'*{slack_escape(name)}:* {slack_escape(value)}' for name, value in item.facts)
    blocks: list[dict[str, Any]] = [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*{title}*'}}]
    if lines:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': lines}})
    if item.url:
        blocks.append(
            {
                'type': 'actions',
                'elements': [
                    {'type': 'button', 'text': {'type': 'plain_text', 'text': item.button[:75]}, 'url': item.url}
                ],
            }
        )
    text = f'{title} <{item.url}|{slack_escape(item.button)}>' if item.url else title
    return {'text': text, 'blocks': blocks}


def teams_escape(text: str) -> str:
    """
    Teams renders a little markdown in cards; brackets look the same as full-width ones but make no links, so a
    customer's subject cannot put a link of their own into the card.
    """
    return text.replace('[', '\uff3b').replace(']', '\uff3d')


def teams_message(item: ChatNotice) -> dict[str, Any]:
    """An Adaptive Card with the notice as a title and a list of facts."""
    body: list[dict[str, Any]] = [
        {'type': 'TextBlock', 'text': teams_escape(item.title), 'weight': 'Bolder', 'size': 'Medium', 'wrap': True}
    ]
    if item.facts:
        body.append(
            {
                'type': 'FactSet',
                'facts': [{'title': teams_escape(name), 'value': teams_escape(value)} for name, value in item.facts],
            }
        )
    card: dict[str, Any] = {
        '$schema': 'http://adaptivecards.io/schemas/adaptive-card.json',
        'type': 'AdaptiveCard',
        'version': '1.4',
        'body': body,
    }
    if item.url:
        card['actions'] = [{'type': 'Action.OpenUrl', 'title': item.button, 'url': item.url}]
    return {
        'type': 'message',
        'attachments': [
            {'contentType': 'application/vnd.microsoft.card.adaptive', 'contentUrl': None, 'content': card}
        ],
    }


def chat_body(format: WebhookFormat, payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """The body for a chat format; None for `json` (the event goes as it is)."""
    if format == 'slack':
        return slack_message(notice(payload))
    if format == 'teams':
        return teams_message(notice(payload))
    return None
