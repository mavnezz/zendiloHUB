from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# The networks a reverse proxy usually talks to the app from (Docker, LAN, localhost).
PRIVATE_NETWORKS = '127.0.0.1/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7'

LOG_LEVELS = ('debug', 'info', 'warning', 'error')

SMTP_SECURITY = ('starttls', 'ssl', 'none')

type SmtpSecurity = Literal['starttls', 'ssl', 'none']


@dataclass(frozen=True, kw_only=True)
class MailConfig:
    host: str | None
    """None: e-mails are only logged (development)."""
    port: int
    username: str | None
    password: str | None
    security: SmtpSecurity
    sender: str


@dataclass(frozen=True, kw_only=True)
class InitialAdmin:
    """The administrator the app creates on start while there is none (the last one can never be removed)."""

    email: str
    password: str = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class OAuthApp:
    """An app registered at a mail provider (Google, Microsoft), for connecting mailboxes with OAuth."""

    client_id: str
    client_secret: str = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class AppConfig:
    """
    Infrastructure settings, all from `ZENDILOHUB_*` environment variables with sensible
    defaults. Everything else (organizations, users, queues) lives in the database.
    """

    host: str
    port: int
    log_level: str
    database_url: str
    redis_url: str
    data_dir: Path
    """Local files (uploads, the generated secret key); shared by the app and the workers."""
    web_dir: Path | None
    """The built web app; None serves the API only."""
    public_url: str | None
    """Only used for absolute links in e-mails; the app itself uses relative URLs."""
    trusted_proxies: str
    """Comma-separated addresses/networks whose X-Forwarded-* headers are trusted."""
    api_docs: bool
    max_upload_bytes: int
    timezone: ZoneInfo
    """The platform's time zone; new tenants start with it."""
    secret_key: str | None
    """Keys hashes and encrypts secrets at rest; generated into the data directory if not set."""
    audit_retention_days: int
    """Entries of the audit log are deleted after this many days."""
    multi_tenant: bool
    """
    False (self-hosting, the default): one organization, made by the setup wizard; nobody signs up.
    True (SaaS): people sign up and create organizations of their own.
    """
    mail: MailConfig
    initial_admin: InitialAdmin | None
    """None: the first administrator comes from the setup wizard or `zendilohub make-admin`."""
    anthropic_api_key: str | None = field(default=None, repr=False)
    """Turns on the AI assistant (ticket summaries, draft replies) with Claude; None: it is off."""
    ai_model: str = 'claude-opus-5-5'
    google_oauth: OAuthApp | None = None
    """Connect Gmail / Google Workspace mailboxes with OAuth; None: not offered."""
    microsoft_oauth: OAuthApp | None = None
    """Connect Microsoft 365 / Outlook mailboxes with OAuth; None: not offered."""
    microsoft_tenant: str = 'common'
    """The Microsoft Entra tenant the app signs in with: `common`, `organizations` or a tenant id."""


def load_config(env: Mapping[str, str]) -> AppConfig:
    log_level = env.get('ZENDILOHUB_LOG_LEVEL') or 'info'
    if log_level.lower() not in LOG_LEVELS:
        raise ValueError(f'ZENDILOHUB_LOG_LEVEL must be one of {", ".join(LOG_LEVELS)}, got "{log_level}"')
    web_dir = env.get('ZENDILOHUB_WEB_DIR')
    public_url = _url('ZENDILOHUB_PUBLIC_URL', env.get('ZENDILOHUB_PUBLIC_URL'))
    mail = _mail(env)
    if mail.host and not public_url:
        raise ValueError('ZENDILOHUB_PUBLIC_URL is required to send e-mails: their links need the public address')
    return AppConfig(
        host=env.get('ZENDILOHUB_HOST') or '0.0.0.0',
        port=_port(env.get('ZENDILOHUB_PORT')),
        log_level=log_level.lower(),
        database_url=env.get('ZENDILOHUB_DATABASE_URL')
        or 'postgresql://zendilohub:zendilohub@localhost:5432/zendilohub',
        redis_url=env.get('ZENDILOHUB_REDIS_URL') or 'redis://localhost:6379/0',
        data_dir=Path(env.get('ZENDILOHUB_DATA_DIR') or 'data').resolve(),
        web_dir=Path(web_dir).resolve() if web_dir else None,
        public_url=public_url,
        trusted_proxies=env.get('ZENDILOHUB_TRUSTED_PROXIES') or PRIVATE_NETWORKS,
        api_docs=_boolean('ZENDILOHUB_API_DOCS', env.get('ZENDILOHUB_API_DOCS'), True),
        max_upload_bytes=_integer('ZENDILOHUB_MAX_UPLOAD_MB', env.get('ZENDILOHUB_MAX_UPLOAD_MB'), 25, 1) * 1024 * 1024,
        timezone=_timezone(env.get('ZENDILOHUB_TIMEZONE') or 'Europe/Berlin'),
        secret_key=env.get('ZENDILOHUB_SECRET_KEY') or None,
        audit_retention_days=_integer(
            'ZENDILOHUB_AUDIT_RETENTION_DAYS', env.get('ZENDILOHUB_AUDIT_RETENTION_DAYS'), 365, 1
        ),
        multi_tenant=_boolean('ZENDILOHUB_MULTI_TENANT', env.get('ZENDILOHUB_MULTI_TENANT'), False),
        mail=mail,
        initial_admin=_initial_admin(env),
        anthropic_api_key=(env.get('ZENDILOHUB_ANTHROPIC_API_KEY') or '').strip() or None,
        ai_model=(env.get('ZENDILOHUB_AI_MODEL') or '').strip() or 'claude-opus-5-5',
        google_oauth=_oauth_app(env, 'GOOGLE'),
        microsoft_oauth=_oauth_app(env, 'MICROSOFT'),
        microsoft_tenant=_microsoft_tenant(env.get('ZENDILOHUB_MICROSOFT_TENANT')),
    )


def _oauth_app(env: Mapping[str, str], provider: str) -> OAuthApp | None:
    client_id = (env.get(f'ZENDILOHUB_{provider}_CLIENT_ID') or '').strip()
    client_secret = (env.get(f'ZENDILOHUB_{provider}_CLIENT_SECRET') or '').strip()
    if bool(client_id) != bool(client_secret):
        raise ValueError(
            f'Set both ZENDILOHUB_{provider}_CLIENT_ID and ZENDILOHUB_{provider}_CLIENT_SECRET, or neither'
        )
    return OAuthApp(client_id=client_id, client_secret=client_secret) if client_id else None


def _microsoft_tenant(raw: str | None) -> str:
    tenant = (raw or '').strip() or 'common'
    if not all(char.isalnum() or char in '-.' for char in tenant):
        raise ValueError(f'ZENDILOHUB_MICROSOFT_TENANT must be common, organizations or a tenant id, got "{tenant}"')
    return tenant


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        raise ValueError(f'ZENDILOHUB_TIMEZONE must be a time zone such as Europe/Berlin, got "{name}"') from None


def _initial_admin(env: Mapping[str, str]) -> InitialAdmin | None:
    email = (env.get('ZENDILOHUB_ADMIN_EMAIL') or '').strip()
    password = env.get('ZENDILOHUB_ADMIN_PASSWORD') or ''
    if not email and not password:
        return None
    if not email or not password:
        raise ValueError('ZENDILOHUB_ADMIN_EMAIL and ZENDILOHUB_ADMIN_PASSWORD go together: set both or neither')
    return InitialAdmin(email=email, password=password)


def _mail(env: Mapping[str, str]) -> MailConfig:
    security = (env.get('ZENDILOHUB_SMTP_SECURITY') or 'starttls').lower()
    if security not in SMTP_SECURITY:
        raise ValueError(f'ZENDILOHUB_SMTP_SECURITY must be one of {", ".join(SMTP_SECURITY)}, got "{security}"')
    default_port = {'starttls': '587', 'ssl': '465', 'none': '25'}[security]
    return MailConfig(
        host=env.get('ZENDILOHUB_SMTP_HOST') or None,
        port=_port(env.get('ZENDILOHUB_SMTP_PORT') or default_port, 'ZENDILOHUB_SMTP_PORT'),
        username=env.get('ZENDILOHUB_SMTP_USERNAME') or None,
        password=env.get('ZENDILOHUB_SMTP_PASSWORD') or None,
        security=security,  # type: ignore[arg-type]
        sender=env.get('ZENDILOHUB_MAIL_FROM') or 'zendiloHUB <noreply@localhost>',
    )


def _port(raw: str | None, name: str = 'ZENDILOHUB_PORT') -> int:
    if not raw:
        return 8080
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ValueError(f'{name} must be a port number between 1 and 65535, got "{raw}"')
    return int(raw)


def _integer(name: str, raw: str | None, fallback: int, minimum: int) -> int:
    if not raw:
        return fallback
    if not raw.isdigit() or int(raw) < minimum:
        raise ValueError(f'{name} must be a whole number of at least {minimum}, got "{raw}"')
    return int(raw)


def _boolean(name: str, raw: str | None, fallback: bool) -> bool:
    if not raw:
        return fallback
    if raw.lower() in ('1', 'true', 'yes', 'on'):
        return True
    if raw.lower() in ('0', 'false', 'no', 'off'):
        return False
    raise ValueError(f'{name} must be true or false, got "{raw}"')


def _url(name: str, raw: str | None) -> str | None:
    if not raw:
        return None
    if not raw.startswith(('http://', 'https://')):
        raise ValueError(f'{name} must start with http:// or https://, got "{raw}"')
    return raw.rstrip('/')
