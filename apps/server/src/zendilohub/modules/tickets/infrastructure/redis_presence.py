from redis.asyncio import Redis

from zendilohub.core.domain.clock import Clock

SECONDS = 30
"""How long someone counts as looking at a ticket after their last sign of life."""


class RedisPresence:
    """Who looks at which ticket: a hash per ticket, user → last seen (and whether they write)."""

    def __init__(self, redis: Redis, clock: Clock) -> None:
        self._redis = redis
        self._clock = clock

    async def here(self, tenant_id: str, ticket_id: str, user_id: str, *, writing: bool) -> list[tuple[str, bool]]:
        key = f'presence:{tenant_id}:{ticket_id}'
        now = self._clock.now().timestamp()
        await self._redis.hset(key, user_id, f'{now}:{int(writing)}')
        await self._redis.expire(key, SECONDS * 2)
        entries = await self._redis.hgetall(key)
        others: list[tuple[str, bool]] = []
        for raw_user, raw_value in entries.items():
            other = raw_user.decode() if isinstance(raw_user, bytes) else raw_user
            value = raw_value.decode() if isinstance(raw_value, bytes) else raw_value
            seen, _, flag = value.partition(':')
            if other == user_id:
                continue
            if now - float(seen) > SECONDS:
                await self._redis.hdel(key, other)
                continue
            others.append((other, flag == '1'))
        return sorted(others)
