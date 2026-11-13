from datetime import UTC, datetime, timedelta

import argon2
import pytest

from support.fakes import MemoryMailer
from zendilohub.core.database.database import Database
from zendilohub.core.database.migration import sql_migrations
from zendilohub.core.database.migrator import Migrator
from zendilohub.core.domain.mailer import MailMessage
from zendilohub.modules.identity.domain.exceptions import EmailTakenError, InvalidEmailError, WeakPasswordError
from zendilohub.modules.identity.domain.models.email import normalize_email
from zendilohub.modules.identity.domain.models.password_policy import check_password
from zendilohub.modules.identity.domain.models.registration import Registration
from zendilohub.modules.identity.domain.models.session import Session
from zendilohub.modules.identity.domain.models.user import User
from zendilohub.modules.identity.identity_module import MIGRATIONS
from zendilohub.modules.identity.infrastructure.mail_notifier import TEMPLATES, MailAccountNotifier
from zendilohub.modules.identity.infrastructure.postgres_users import PostgresUserRepository
from zendilohub.modules.identity.infrastructure.security import Argon2PasswordHasher, Sha256TokenService

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def _user(**overrides: object) -> User:
    registration = Registration.start(id='r1', email='ada@example.org', password_hash='hash', locale='en', now=NOW)
    user = User.from_registration(id='00000000-0000-7000-8000-000000000001', registration=registration, now=NOW)
    for name, value in overrides.items():
        setattr(user, name, value)
    return user


@pytest.mark.parametrize(('raw', 'email'), [(' Ada@Example.ORG ', 'ada@example.org'), ('a.b+c@d.co', 'a.b+c@d.co')])
def test_normalizes_e_mail_addresses(raw: str, email: str) -> None:
    assert normalize_email(raw) == email


@pytest.mark.parametrize(
    'raw', ['', 'ada', 'ada@example', 'ada @example.org', 'ada@example.', f'{"a" * 250}@example.org']
)
def test_rejects_invalid_e_mail_addresses(raw: str) -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email(raw)


def test_checks_the_password_length() -> None:
    check_password('a' * 10)
    check_password('a' * 128)
    for password in ('a' * 9, 'a' * 129):
        with pytest.raises(WeakPasswordError):
            check_password(password)


def test_models() -> None:
    session = Session.start(id='s1', user_id='u1', now=NOW)
    assert not session.is_expired(NOW + timedelta(days=29))
    assert session.is_expired(NOW + timedelta(days=30))

    registration = Registration.start(id='r1', email='ada@example.org', password_hash='h', locale='de', now=NOW)
    renewed = registration.renew('r2', NOW + timedelta(hours=47))
    assert (renewed.id, renewed.email, renewed.created_at) == ('r2', 'ada@example.org', NOW)
    assert not renewed.is_expired(NOW + timedelta(hours=94))

    user = _user()
    assert user.email_verified_at == NOW
    assert user.locale == 'en'
    assert not user.is_admin


async def test_hashes_and_verifies_passwords() -> None:
    hasher = Argon2PasswordHasher(argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))
    password_hash = await hasher.hash('correct horse battery')
    assert password_hash.startswith('$argon2id$')
    assert await hasher.verify('correct horse battery', password_hash)
    assert not await hasher.verify('wrong', password_hash)
    assert not await hasher.verify('wrong', 'not a hash')
    assert not hasher.needs_rehash(password_hash)
    assert hasher.needs_rehash('not a hash')
    assert Argon2PasswordHasher().needs_rehash(password_hash)


def test_issues_random_tokens_and_stores_only_their_hash() -> None:
    tokens = Sha256TokenService()
    first, second = tokens.issue(), tokens.issue()
    assert first.token != second.token
    assert len(first.token) >= 40
    assert first.id == tokens.id_of(first.token)
    assert first.token not in first.id


async def test_sends_every_account_e_mail_in_both_languages() -> None:
    mailer = MemoryMailer()
    notifier = MailAccountNotifier(mailer)
    registration = Registration.start(id='r1', email='ada@example.org', password_hash='h', locale='de', now=NOW)
    await notifier.confirm_registration(registration, 'https://x/verify')
    await notifier.already_registered(_user(), 'https://x/login')
    await notifier.reset_password(_user(locale='de'), 'https://x/reset')

    assert [(mail.subject, mail.to) for mail in mailer.sent] == [
        ('Bestätige dein zendiloHUB-Konto', 'ada@example.org'),
        ('Your zendiloHUB account', 'ada@example.org'),
        ('Setze dein zendiloHUB-Passwort zurück', 'ada@example.org'),
    ]
    assert all(isinstance(mail, MailMessage) and 'https://x/' in mail.text for mail in mailer.sent)
    assert all(set(texts) == {'de', 'en'} for texts in TEMPLATES.values())


async def test_the_repository_refuses_a_second_account_for_an_address(empty_db: Database) -> None:
    await Migrator(empty_db).run(sql_migrations(MIGRATIONS))
    users = PostgresUserRepository(empty_db)
    await users.save(_user())
    with pytest.raises(EmailTakenError):
        await users.save(_user(id='00000000-0000-7000-8000-000000000002'))


def test_rejects_control_characters_in_addresses() -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email('ada\x00@example.org')
