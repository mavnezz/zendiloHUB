import logging
import smtplib
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from redis.asyncio import Redis

from support.fakes import FakeClock
from zendilohub.core.config import MailConfig, load_config
from zendilohub.core.domain.mailer import MailMessage
from zendilohub.core.domain.rate_limited import TooManyRequestsError
from zendilohub.core.domain.rate_limiter import RateLimit
from zendilohub.core.infrastructure.mailers import LogMailer, SmtpMailer
from zendilohub.core.infrastructure.redis_rate_limiter import RedisRateLimiter

MESSAGE = MailMessage(to='ada@example.org', subject='Hello', text='Hi Ada,\n\nhttps://print.example.org/x')


class FakeSmtp:
    instances: ClassVar[list[FakeSmtp]] = []

    def __init__(self, host: str, port: int, timeout: int, **kwargs: Any) -> None:
        self.host, self.port, self.kwargs = host, port, kwargs
        self.calls: list[str] = []
        self.sent: list[Any] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *args: object) -> None:
        self.calls.append('quit')

    def starttls(self, context: object) -> None:
        self.calls.append('starttls')

    def login(self, username: str, password: str) -> None:
        self.calls.append(f'login {username} {password}')

    def send_message(self, mail: Any) -> None:
        self.sent.append(mail)


def _config(**overrides: Any) -> MailConfig:
    values: dict[str, Any] = {
        'host': 'smtp.example.org',
        'port': 587,
        'username': 'zendilohub',
        'password': 'secret',
        'security': 'starttls',
        'sender': 'zendiloHUB <noreply@print.example.org>',
    }
    return MailConfig(**(values | overrides))


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSmtp.instances = []
    monkeypatch.setattr(smtplib, 'SMTP', FakeSmtp)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', FakeSmtp)


async def test_sends_via_smtp_with_starttls_and_login() -> None:
    await SmtpMailer(_config()).send(MESSAGE)

    [smtp] = FakeSmtp.instances
    assert (smtp.host, smtp.port) == ('smtp.example.org', 587)
    assert smtp.calls == ['starttls', 'login zendilohub secret', 'quit']
    [mail] = smtp.sent
    assert mail['From'] == 'zendiloHUB <noreply@print.example.org>'
    assert mail['To'] == 'ada@example.org'
    assert mail['Subject'] == 'Hello'
    assert mail['Message-ID'].endswith('@print.example.org>')
    assert 'https://print.example.org/x' in mail.get_content()


async def test_sends_via_implicit_tls_or_plain_smtp_without_login() -> None:
    await SmtpMailer(_config(security='ssl', port=465, username=None)).send(MESSAGE)
    await SmtpMailer(_config(security='none', port=25, username=None)).send(MESSAGE)

    ssl, plain = FakeSmtp.instances
    assert 'context' in ssl.kwargs
    assert ssl.calls == ['quit']
    assert plain.kwargs == {}
    assert plain.calls == ['quit']


async def test_logs_e_mails_without_smtp(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        await LogMailer().send(MESSAGE)
    [record] = [record for record in caplog.records if record.getMessage().startswith('E-mail not sent')]
    assert record.__dict__['to'] == 'ada@example.org'
    assert 'https://print.example.org/x' in record.__dict__['text']


def test_reads_the_mail_settings() -> None:
    config = load_config(
        {
            'ZENDILOHUB_SMTP_HOST': 'smtp.example.org',
            'ZENDILOHUB_SMTP_SECURITY': 'SSL',
            'ZENDILOHUB_SMTP_USERNAME': 'zendilohub',
            'ZENDILOHUB_SMTP_PASSWORD': 'secret',
            'ZENDILOHUB_MAIL_FROM': 'zendiloHUB <hello@print.example.org>',
            'ZENDILOHUB_PUBLIC_URL': 'https://print.example.org',
        }
    )
    assert config.mail == _config(security='ssl', port=465, sender='zendiloHUB <hello@print.example.org>')
    assert load_config({}).mail.host is None
    assert load_config({'ZENDILOHUB_SMTP_SECURITY': 'none'}).mail.port == 25
    assert load_config({'ZENDILOHUB_SMTP_PORT': '2525'}).mail.port == 2525


@pytest.mark.parametrize(
    ('env', 'message'),
    [
        ({'ZENDILOHUB_SMTP_HOST': 'smtp.example.org'}, 'ZENDILOHUB_PUBLIC_URL is required to send e-mails'),
        ({'ZENDILOHUB_SMTP_SECURITY': 'tls'}, 'ZENDILOHUB_SMTP_SECURITY must be one of'),
        ({'ZENDILOHUB_SMTP_PORT': '0'}, 'ZENDILOHUB_SMTP_PORT must be a port number'),
    ],
)
def test_rejects_invalid_mail_settings(env: dict[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_config(env)


LIMIT = RateLimit('test', limit=3, window_seconds=60)


async def test_counts_hits_per_window(redis: Redis) -> None:
    clock = FakeClock(datetime(2026, 10, 22, 12, 0, 10, tzinfo=UTC))
    limiter = RedisRateLimiter(redis, clock)

    statuses = [await limiter.hit(LIMIT, 'ada@example.org') for _ in range(4)]
    assert [status.allowed for status in statuses] == [True, True, True, False]
    assert [status.remaining for status in statuses] == [2, 1, 0, 0]
    assert statuses[0].retry_after == 50
    assert not (await limiter.peek(LIMIT, 'ada@example.org')).allowed
    assert (await limiter.peek(LIMIT, 'grace@example.org')).allowed

    clock.advance(seconds=50)
    assert (await limiter.peek(LIMIT, 'ada@example.org')).remaining == 3


async def test_resets_and_does_not_store_subjects_in_plain_text(redis: Redis) -> None:
    limiter = RedisRateLimiter(redis, FakeClock())
    await limiter.hit(LIMIT, 'ada@example.org')
    keys = [key.decode() if isinstance(key, bytes) else key for key in await redis.keys('*')]
    assert len(keys) == 1
    assert 'ada' not in keys[0]
    assert await redis.ttl(keys[0]) > 0

    await limiter.reset(LIMIT, 'ada@example.org')
    assert await redis.keys('*') == []


def test_too_many_requests_says_when_to_retry() -> None:
    error = TooManyRequestsError(61)
    assert error.params == {'retry_after': 61, 'minutes': 2}
    assert TooManyRequestsError(0).params == {'retry_after': 1, 'minutes': 1}
