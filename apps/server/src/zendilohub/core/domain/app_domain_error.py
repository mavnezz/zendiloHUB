from collections.abc import Mapping
from typing import ClassVar, Literal

type ErrorKind = Literal[
    'validation',
    'unauthenticated',
    'forbidden',
    'not_found',
    'conflict',
    'too_large',
    'unsupported',
    'rate_limited',
    'unavailable',
    'upstream',
]

type ErrorParams = Mapping[str, str | int | float]


class AppDomainError(Exception):
    """
    Base class for expected, user-facing errors. `code` is a stable machine-readable
    identifier the web app translates (with `params`); `message` is an English
    fallback for logs and API clients. `kind` tells adapters (HTTP, CLI) how to report it.
    """

    kind: ClassVar[ErrorKind]

    def __init__(self, code: str, message: str, params: ErrorParams | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.params: ErrorParams = dict(params or {})


class ValidationError(AppDomainError):
    kind = 'validation'


class UnauthenticatedError(AppDomainError):
    kind = 'unauthenticated'


class ForbiddenError(AppDomainError):
    kind = 'forbidden'


class NotFoundError(AppDomainError):
    kind = 'not_found'


class ConflictError(AppDomainError):
    kind = 'conflict'


class TooLargeError(AppDomainError):
    """An upload or a result exceeds a size limit."""

    kind = 'too_large'


class UnsupportedError(AppDomainError):
    """E.g. a file type that is not accepted."""

    kind = 'unsupported'


class RateLimitedError(AppDomainError):
    """Too many attempts or a used-up quota; try again later."""

    kind = 'rate_limited'


class UnavailableError(AppDomainError):
    """A dependency (database, queue) is currently not reachable."""

    kind = 'unavailable'


class UpstreamError(AppDomainError):
    """A dependency answered, but with an error."""

    kind = 'upstream'
