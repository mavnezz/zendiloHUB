"""The real IMAP and SMTP adapters against GreenMail, a mail server for tests (in Docker)."""

import imaplib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import ClassVar

import pytest

from support.mail_server import email
from zendilohub.modules.channels.domain.models.account import AccountSettings, EmailAccount, Server
from zendilohub.modules.channels.domain.ports.services import Credential, MailboxError, OutgoingMail
from zendilohub.modules.channels.infrastructure.mail_servers import ImapMailbox, Nh3Cleaner, SmtpOutbox, xoauth2

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


@pytest.fixture(scope='module')
def greenmail() -> Iterator[tuple[str, int, int]]:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    container = (
        DockerContainer('greenmail/standalone:2.1.3')
        .with_env(
            'GREENMAIL_OPTS',
            '-Dgreenmail.setup.test.smtp -Dgreenmail.setup.test.imap -Dgreenmail.hostname=0.0.0.0 '
            '-Dgreenmail.auth.disabled',
        )
        .with_exposed_ports(3025, 3143)
    )
    with container:
        wait_for_logs(container, 'Starting GreenMail', timeout=60)
        host = container.get_container_host_ip()
        yield host, int(container.get_exposed_port(3025)), int(container.get_exposed_port(3143))


def account(host: str, smtp_port: int, imap_port: int, address: str = 'support@acme.example') -> EmailAccount:
    return EmailAccount.create(
        id='a1',
        tenant_id='t1',
        settings=AccountSettings(
            name='Support',
            address=address,
            display_name='Acme Support',
            queue_id='q1',
            imap=Server(host=host, port=imap_port, security='none', username=address),
            smtp=Server(host=host, port=smtp_port, security='none', username=''),
        ),
        now=NOW,
    )


async def test_sends_and_fetches_mail(greenmail: tuple[str, int, int]) -> None:
    host, smtp_port, imap_port = greenmail
    support = account(host, smtp_port, imap_port)
    outbox, mailbox = SmtpOutbox(), ImapMailbox()
    await outbox.probe(support, Credential(''))
    await mailbox.probe(support, Credential('any'))

    await outbox.send(
        support,
        Credential(''),
        OutgoingMail(
            sender=support.sender,
            to=('support@acme.example',),
            subject='Re: Printer broken [#1001]',
            text='Please restart it.',
            message_id='<r1@acme.example>',
            in_reply_to='<m1@customer.example>',
            references=('<m1@customer.example>',),
            automatic=True,
        ),
    )
    first = await mailbox.fetch(support, Credential('any'), after_uid=0, uid_validity=None, limit=10)
    assert len(first.messages) == 1
    uid, raw = first.messages[0]
    assert b'Auto-Submitted: auto-replied' in raw
    assert b'In-Reply-To: <m1@customer.example>' in raw

    # Seen and older mails are not fetched again; the next one is.
    await outbox.send(
        support,
        Credential(''),
        OutgoingMail(
            sender=support.address, to=('support@acme.example',), subject='Two', text='2', message_id='<r2@x>'
        ),
    )
    second = await mailbox.fetch(support, Credential('any'), after_uid=uid, uid_validity=first.uid_validity, limit=10)
    assert [b'Subject: Two' in each[1] for each in second.messages] == [True]


async def test_explains_why_servers_fail(greenmail: tuple[str, int, int]) -> None:
    host, smtp_port, imap_port = greenmail
    wrong_ports = account(host, imap_port, smtp_port)
    with pytest.raises(MailboxError):
        await ImapMailbox().probe(wrong_ports, Credential('any'))
    unknown = account('mail.does-not-exist.invalid', smtp_port, imap_port)
    with pytest.raises(MailboxError, match='unknown'):
        await SmtpOutbox().probe(unknown, Credential(''))
    folder = account(host, smtp_port, imap_port)
    folder.folder = 'Nowhere'
    with pytest.raises(MailboxError, match='Nowhere'):
        await ImapMailbox().probe(folder, Credential('any'))
    tls = account(host, smtp_port, imap_port)
    tls.smtp = Server(host=host, port=smtp_port, security='starttls', username='')
    with pytest.raises(MailboxError):
        await SmtpOutbox().probe(tls, Credential(''))


async def test_logs_in_with_oauth(greenmail: tuple[str, int, int], monkeypatch: pytest.MonkeyPatch) -> None:
    host, smtp_port, imap_port = greenmail
    support = account(host, smtp_port, imap_port)
    support.smtp = Server(host=host, port=smtp_port, security='none', username='support@acme.example')
    token = Credential('ya29.token', oauth=True)
    # GreenMail speaks XOAUTH2 by SMTP only; its IMAP side is a stand-in that records the exchange.
    await SmtpOutbox().probe(support, token)

    answers: list[bytes] = []

    class Imap:
        error = imaplib.IMAP4.error
        untagged_responses: ClassVar[dict[str, list[bytes]]] = {'OK': [b'[UIDVALIDITY 7]']}

        def __init__(self, *_: object, **__: object) -> None:
            pass

        def authenticate(self, mechanism: str, answer: Callable[[bytes], bytes]) -> None:
            assert mechanism == 'XOAUTH2'
            answers.append(answer(b''))

        def login(self, *_: str) -> None:
            raise AssertionError('no password login with OAuth')

        def select(self, _folder: str) -> tuple[str, list[bytes]]:
            return 'OK', [b'1']

        def status(self, *_: str) -> tuple[str, list[bytes]]:
            return 'OK', [b'']

        def logout(self) -> None:
            pass

    monkeypatch.setattr(imaplib, 'IMAP4', Imap)
    await ImapMailbox().probe(support, token)
    assert answers == [xoauth2('support@acme.example', 'ya29.token').encode()]


def test_builds_the_xoauth2_response() -> None:
    assert (
        xoauth2('support@acme.example', 'ya29.token') == 'user=support@acme.example\x01auth=Bearer ya29.token\x01\x01'
    )


def test_cleans_html() -> None:
    cleaned = Nh3Cleaner().clean(
        '<p onclick="x()">Hi <a href="javascript:alert(1)">x</a> <a href="https://acme.example">y</a></p>'
        '<img src="https://tracker.example/pixel.gif"><style>p{}</style>'
    )
    assert cleaned == (
        '<p>Hi <a rel="noopener noreferrer nofollow">x</a> '
        '<a href="https://acme.example" rel="noopener noreferrer nofollow">y</a></p>'
    )
    assert email(text='x').startswith(b'From:')
