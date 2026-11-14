from zendilohub.core.domain.rate_limited import TooManyRequestsError
from zendilohub.core.domain.rate_limiter import RateLimit, RateLimiter

# Password guessing: failed logins per address and per client.
LOGIN_FAILURES_PER_EMAIL = RateLimit('login-email', limit=10, window_seconds=15 * 60)
LOGIN_FAILURES_PER_CLIENT = RateLimit('login-client', limit=30, window_seconds=15 * 60)
# E-mails we send on request: nobody may flood an inbox or use us for spam.
MAILS_PER_EMAIL = RateLimit('account-mail-email', limit=5, window_seconds=60 * 60)
MAILS_PER_CLIENT = RateLimit('account-mail-client', limit=20, window_seconds=60 * 60)


async def hit_all(limiter: RateLimiter, *hits: tuple[RateLimit, str]) -> None:
    """Counts a hit for every (limit, subject); raises if any of them is exceeded."""
    statuses = [await limiter.hit(limit, subject) for limit, subject in hits]
    blocked = [status.retry_after for status in statuses if not status.allowed]
    if blocked:
        raise TooManyRequestsError(max(blocked))


async def check_all(limiter: RateLimiter, *checks: tuple[RateLimit, str]) -> None:
    """Raises if any (limit, subject) is used up, without counting."""
    statuses = [await limiter.peek(limit, subject) for limit, subject in checks]
    blocked = [status.retry_after for status in statuses if not status.allowed]
    if blocked:
        raise TooManyRequestsError(max(blocked))


# Guessing the six digits of a two-factor code: wrong codes per account.
TWO_FACTOR_FAILURES_PER_USER = RateLimit('two-factor-user', limit=10, window_seconds=15 * 60)
