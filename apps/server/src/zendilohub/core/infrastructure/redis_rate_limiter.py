import hashlib

from redis.asyncio import Redis

from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.rate_limiter import RateLimit, RateLimitStatus


class RedisRateLimiter:
    """Fixed windows in Redis, so the limits hold across processes and restarts."""

    def __init__(self, redis: Redis, clock: Clock, prefix: str = 'zendilohub:ratelimit') -> None:
        self._redis = redis
        self._clock = clock
        self._prefix = prefix

    async def hit(self, limit: RateLimit, subject: str) -> RateLimitStatus:
        key, retry_after = self._key(limit, subject)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, retry_after + 1)
            count, _ = await pipe.execute()
        return RateLimitStatus(int(count) <= limit.limit, max(0, limit.limit - int(count)), retry_after)

    async def peek(self, limit: RateLimit, subject: str) -> RateLimitStatus:
        key, retry_after = self._key(limit, subject)
        count = int(await self._redis.get(key) or 0)
        return RateLimitStatus(count < limit.limit, max(0, limit.limit - count), retry_after)

    async def reset(self, limit: RateLimit, subject: str) -> None:
        key, _ = self._key(limit, subject)
        await self._redis.delete(key)

    def _key(self, limit: RateLimit, subject: str) -> tuple[str, int]:
        now = int(self._clock.now().timestamp())
        window = now // limit.window_seconds
        retry_after = (window + 1) * limit.window_seconds - now
        # Hashed: subjects are e-mail and IP addresses, which do not belong into Redis in plain text.
        digest = hashlib.sha256(subject.encode()).hexdigest()[:32]
        return f'{self._prefix}:{limit.name}:{digest}:{window}', retry_after
