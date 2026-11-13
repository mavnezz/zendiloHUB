import re

# No blanks and no control characters (which the database would not store either).
_PATTERN = re.compile(r'^[^@\s\x00-\x1f\x7f]+@[^@\s\x00-\x1f\x7f]+\.[^@\s\x00-\x1f\x7f.]+$')

MAX_LENGTH = 254


def normalized_email(raw: str) -> str | None:
    """E-mail addresses are compared and stored trimmed and in lower case; None if it is no valid address."""
    email = raw.strip().lower()
    if len(email) > MAX_LENGTH or not _PATTERN.match(email):
        return None
    return email
