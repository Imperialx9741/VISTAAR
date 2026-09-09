"""Redis-backed access-token (JTI) denylist, used on logout.

Ephemeral by design — entries expire at the token's natural expiry (``ttl``
below), so this is safe to lose on Redis restart (worst case: a logged-out
token remains usable for up to its remaining natural lifetime, i.e. no
worse than not having a denylist at all — Redis is never the source of
truth here, per the task's REDIS section).
"""

from __future__ import annotations

from redis.asyncio import Redis

_DENYLIST_KEY = "identity:auth:denylist:{jti}"


class RedisAccessTokenDenylist:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def revoke(self, jti: str, *, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return  # already expired naturally; nothing to deny.
        await self._redis.set(_DENYLIST_KEY.format(jti=jti), "1", ex=ttl_seconds)

    async def is_revoked(self, jti: str) -> bool:
        return bool(await self._redis.exists(_DENYLIST_KEY.format(jti=jti)))
