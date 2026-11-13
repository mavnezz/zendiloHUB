from zendilohub.core.domain.email_address import normalized_email

from ..exceptions import InvalidEmailError


def normalize_email(raw: str) -> str:
    """E-mail addresses are compared and stored trimmed and in lower case."""
    email = normalized_email(raw)
    if email is None:
        raise InvalidEmailError()
    return email
