"""Checks shared by contacts and companies."""

import re

from zendilohub.core.domain.email_address import normalized_email

NAME_MAX = 200
NOTES_MAX = 5000
PHONE_MAX = 40

_PHONE = re.compile(r'^\+?[0-9 ()./-]{3,40}$')
_DOMAIN = re.compile(r'^(?=.{3,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$')


def clean_name(raw: str) -> str:
    return ' '.join(raw.split())


class InvalidValueError(ValueError):
    """Raised by the `clean_…` functions; the models turn it into their own error."""


def clean_email(raw: str | None) -> str | None:
    """The normalized address, None for none."""
    if raw is None or not raw.strip():
        return None
    email = normalized_email(raw)
    if email is None:
        raise InvalidValueError('email')
    return email


def clean_phone(raw: str | None) -> str | None:
    """Digits, `+` and the usual separators, None for none."""
    if raw is None or not raw.strip():
        return None
    phone = ' '.join(raw.split())
    if not _PHONE.match(phone):
        raise InvalidValueError('phone')
    return phone


def clean_domain(raw: str | None) -> str | None:
    """`example.org` (also from `@example.org` or `www.example.org`), None for none."""
    if raw is None or not raw.strip():
        return None
    domain = raw.strip().lower().lstrip('@').removeprefix('www.')
    if not _DOMAIN.match(domain):
        raise InvalidValueError('domain')
    return domain


def domain_of(email: str) -> str:
    return email.rsplit('@', 1)[1]
