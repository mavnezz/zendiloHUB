from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RateLimit:
    """At most `limit` hits per `window_seconds` and subject (an e-mail address, an IP address, …)."""

    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitStatus:
    allowed: bool
    remaining: int
    retry_after: int
    """Seconds until the current window ends."""


class RateLimiter(Protocol):
    async def hit(self, limit: RateLimit, subject: str) -> RateLimitStatus:
        """Counts one hit; `allowed` is False once the limit is exceeded."""
        ...

    async def peek(self, limit: RateLimit, subject: str) -> RateLimitStatus:
        """The status without counting a hit: `allowed` is False once the limit is reached."""
        ...

    async def reset(self, limit: RateLimit, subject: str) -> None: ...
