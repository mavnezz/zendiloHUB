from datetime import UTC, datetime

import pytest

from support.mail_server import email
from zendilohub.modules.channels.domain.exceptions import InvalidAccountError, InvalidFilterError, InvalidTemplateError
from zendilohub.modules.channels.domain.models.account import AccountSettings, EmailAccount, Server
from zendilohub.modules.channels.domain.models.email import html_to_text, parse_email, reply_subject
from zendilohub.modules.channels.domain.models.mail_filter import Condition, FilterActions, MailFilter, route
from zendilohub.modules.channels.domain.models.templates import PersonalSettings, QueueChannel, TextTemplate, render

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
SERVER = Server(host='mail.acme.example', port=993, security='ssl', username='x')


def settings(**overrides: object) -> AccountSettings:
    values: dict[str, object] = {
        'name': 'Support',
        'address': 'support@acme.example',
        'display_name': '',
        'queue_id': 'q1',
        'imap': SERVER,
        'smtp': SERVER,
        **overrides,
    }
    return AccountSettings(**values)  # type: ignore[arg-type]


def test_reads_emails() -> None:
    mail = parse_email(
        email(
            sender='"Carl C." <Carl@Customer.example>',
            to='Support <support@acme.example>, other@acme.example',
            Cc='boss@customer.example',
            subject='Re:  Printer   [#1001]',
            References='<a@x> <b@x>',
            In_Reply_To='<c@x>',
            X_Mailer='Thunderbird',
        )
    )
    assert (mail.from_address, mail.from_name, mail.to, mail.cc) == (
        'carl@customer.example',
        'Carl C.',
        ('support@acme.example', 'other@acme.example'),
        ('boss@customer.example',),
    )
    assert (mail.subject, mail.ticket_number, mail.thread_ids) == (
        'Re: Printer [#1001]',
        1001,
        ['<c@x>', '<b@x>', '<a@x>'],
    )
    assert (mail.automatic, mail.headers['x-mailer']) == (False, 'Thunderbird')
    assert parse_email(b'From: x@y.example\r\n\r\n').ticket_number is None


@pytest.mark.parametrize(
    'headers',
    [
        {'Auto_Submitted': 'auto-generated'},
        {'Precedence': 'junk'},
        {'X_Autoreply': 'yes'},
        {'List_Id': '<news.x>'},
        {'X_Auto_Response_Suppress': 'OOF'},
        {'Return_Path': '<>'},
        {'sender': 'MAILER-DAEMON@acme.example'},
    ],
)
def test_recognizes_robots(headers: dict[str, str]) -> None:
    assert parse_email(email(**headers)).automatic


def test_turns_html_into_text_and_builds_reply_subjects() -> None:
    html = '<html><head><title>T</title><style>p{}</style></head><body><h1>Hi</h1><p>One<br>Two</p><script>x</script></body></html>'
    assert html_to_text(html) == 'Hi\n\nOne\nTwo'
    only_html = parse_email(email(text='', html='<p>Only <b>HTML</b></p>'))
    assert only_html.text == 'Only HTML'
    assert reply_subject('AW: Re: Printer [#1001]', 1001) == 'Re: Printer [#1001]'
    assert reply_subject('Fwd: x', 7) == 'Re: x [#7]'


def test_checks_accounts() -> None:
    account = EmailAccount.create(id='a', tenant_id='t', settings=settings(display_name='Acme'), now=NOW)
    assert account.sender == 'Acme <support@acme.example>'
    for server, field in [
        (Server(host='x', port=0, security='ssl', username=''), 'imap.port'),
        (Server(host='x', port=1, security='tls', username=''), 'imap.security'),  # type: ignore[arg-type]
        (Server(host='x', port=1, security='ssl', username='u' * 255), 'imap.username'),
    ]:
        with pytest.raises(InvalidAccountError) as raised:
            EmailAccount.create(id='a', tenant_id='t', settings=settings(imap=server), now=NOW)
        assert raised.value.params == {'field': field}
    for overrides, field in [({'display_name': 'x' * 81}, 'display_name'), ({'folder': 'x' * 201}, 'folder')]:
        with pytest.raises(InvalidAccountError) as raised:
            EmailAccount.create(id='a', tenant_id='t', settings=settings(**overrides), now=NOW)
        assert raised.value.params == {'field': field}


def test_fills_and_checks_templates() -> None:
    assert render('Hi {{ customer.name }},\n{{agent.title}}\nBye', {'customer.name': 'Carl'}) == 'Hi Carl,\nBye'
    for name, body, field in [(' ', 'x', 'name'), ('x', ' ', 'body'), ('x', '{{x}}', 'body')]:
        with pytest.raises(InvalidTemplateError) as raised:
            TextTemplate.create(id='t', tenant_id='t', kind='signature', name=name, body=body, now=NOW)
        assert raised.value.params['field'] == field
    personal = PersonalSettings(tenant_id='t', user_id='u', name='', title='', signature='')
    for values, field in [
        ({'name': 'x' * 81}, 'name'),
        ({'title': 'x' * 81}, 'title'),
        ({'signature': 'x' * 10_001}, 'signature'),
    ]:
        with pytest.raises(InvalidTemplateError) as raised:
            personal.change(**{'name': '', 'title': '', 'signature': '', **values})
        assert raised.value.params['field'] == field
    for values, field in [
        ({'auto_reply_subject': 'x' * 251}, 'auto_reply_subject'),
        ({'auto_reply_body': 'x' * 10_001}, 'auto_reply_body'),
    ]:
        with pytest.raises(InvalidTemplateError) as raised:
            QueueChannel(tenant_id='t', queue_id='q', **values).check()  # type: ignore[arg-type]
        assert raised.value.params['field'] == field


def mail_filter(conditions: tuple[Condition, ...], actions: FilterActions, **overrides: object) -> MailFilter:
    values: dict[str, object] = {
        'id': 'f',
        'tenant_id': 't',
        'name': 'F',
        'position': 1,
        'active': True,
        'match': 'all',
        'conditions': conditions,
        'actions': actions,
        'stop': False,
        'created_at': NOW,
        'updated_at': NOW,
        **overrides,
    }
    return MailFilter(**values)  # type: ignore[arg-type]


def test_filters_match_and_route() -> None:
    mail = parse_email(email(subject='Invoice 42', text='Please pay', Cc='x@acme.example'))
    invoice = Condition(field='subject', operator='starts_with', value='invoice')
    assert invoice.matches(mail)
    assert Condition(field='cc', operator='equals', value='X@ACME.example').matches(mail)
    assert Condition(field='body', operator='not_contains', value='refund').matches(mail)
    assert not Condition(field='from', operator='ends_with', value='@acme.example').matches(mail)
    tagged = mail_filter((invoice,), FilterActions(tags=('billing',)), stop=True)
    later = mail_filter((invoice,), FilterActions(priority='high'), position=2)
    inactive = mail_filter((invoice,), FilterActions(ignore=True), active=False, position=0)
    assert route([later, tagged, inactive], mail).tags == ('billing',)
    assert route([later, tagged, inactive], mail).priority is None
    for condition, field in [
        (Condition(field='nope', operator='contains', value='x'), 'conditions.field'),  # type: ignore[arg-type]
        (Condition(field='to', operator='nope', value='x'), 'conditions.operator'),  # type: ignore[arg-type]
        (Condition(field='to', operator='contains', value=''), 'conditions.value'),
    ]:
        with pytest.raises(InvalidFilterError) as raised:
            condition.check()
        assert raised.value.params == {'field': field}
    with pytest.raises(InvalidFilterError) as raised:
        mail_filter((), FilterActions(tags=('x',))).check()
    assert raised.value.params == {'field': 'conditions'}
