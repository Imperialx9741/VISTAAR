"""Unit tests for shared/rate_limit.py's generic Redis-backed rate
limiter (security.md §20; security-review-2026-09-02.md finding 4.1).

Against real local Redis, same convention test_identity_api.py's own
RedisOtpRateLimiter-driven tests already use — not a fake/mock client,
since the whole point is proving the real INCR+EXPIRE mechanism works,
not a hand-written stand-in for it. Skips (not fails) when Redis is
genuinely unreachable.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from core.redis import get_redis_client
from shared.rate_limit import RateLimitedError, RateLimiter, rate_limit_key


def _redis_available() -> bool:
    async def _ping() -> bool:
        client = get_redis_client()
        try:
            return await client.ping()
        finally:
            await client.aclose()

    try:
        return asyncio.run(_ping())
    except RedisConnectionError:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis is offline/unreachable (start docker-compose.dev.yml)",
)


def _unique_key(category: str) -> str:
    return rate_limit_key(category=category, identity=str(uuid.uuid4()))


def test_requests_within_the_limit_all_succeed() -> None:
    async def _run() -> None:
        client: Redis = get_redis_client()
        try:
            limiter = RateLimiter(client)
            key = _unique_key("test_within_limit")
            for _ in range(3):
                await limiter.check_and_increment(key=key, limit=3, window_seconds=60)
        finally:
            await client.aclose()

    asyncio.run(_run())


def test_the_request_that_exceeds_the_limit_raises() -> None:
    async def _run() -> None:
        client: Redis = get_redis_client()
        try:
            limiter = RateLimiter(client)
            key = _unique_key("test_exceeds_limit")
            for _ in range(2):
                await limiter.check_and_increment(key=key, limit=2, window_seconds=60)
            with pytest.raises(RateLimitedError):
                await limiter.check_and_increment(key=key, limit=2, window_seconds=60)
        finally:
            await client.aclose()

    asyncio.run(_run())


def test_a_rejected_request_still_counts_and_stays_blocked() -> None:
    """A client that keeps retrying past the limit must not be able to
    reset or extend its own window by continuing to hammer the
    endpoint."""

    async def _run() -> None:
        client: Redis = get_redis_client()
        try:
            limiter = RateLimiter(client)
            key = _unique_key("test_stays_blocked")
            await limiter.check_and_increment(key=key, limit=1, window_seconds=60)
            for _ in range(5):
                with pytest.raises(RateLimitedError):
                    await limiter.check_and_increment(
                        key=key, limit=1, window_seconds=60
                    )
        finally:
            await client.aclose()

    asyncio.run(_run())


def test_different_categories_have_independent_counters_for_the_same_identity() -> None:
    async def _run() -> None:
        client: Redis = get_redis_client()
        try:
            limiter = RateLimiter(client)
            identity = str(uuid.uuid4())
            ride_key = rate_limit_key(category="ride_create", identity=identity)
            wallet_key = rate_limit_key(category="wallet_recharge", identity=identity)

            await limiter.check_and_increment(key=ride_key, limit=1, window_seconds=60)
            with pytest.raises(RateLimitedError):
                await limiter.check_and_increment(
                    key=ride_key, limit=1, window_seconds=60
                )

            # A different category, same identity — must not be blocked
            # by the ride_create counter above.
            await limiter.check_and_increment(
                key=wallet_key, limit=1, window_seconds=60
            )
        finally:
            await client.aclose()

    asyncio.run(_run())


def test_different_identities_have_independent_counters_for_the_same_category() -> None:
    async def _run() -> None:
        client: Redis = get_redis_client()
        try:
            limiter = RateLimiter(client)
            key_a = rate_limit_key(category="ride_create", identity=str(uuid.uuid4()))
            key_b = rate_limit_key(category="ride_create", identity=str(uuid.uuid4()))

            await limiter.check_and_increment(key=key_a, limit=1, window_seconds=60)
            with pytest.raises(RateLimitedError):
                await limiter.check_and_increment(key=key_a, limit=1, window_seconds=60)

            # A different identity, same category — unaffected.
            await limiter.check_and_increment(key=key_b, limit=1, window_seconds=60)
        finally:
            await client.aclose()

    asyncio.run(_run())


def test_rate_limited_error_carries_the_documented_error_code() -> None:
    error = RateLimitedError()
    assert error.code == "RATE_LIMITED"
    assert error.message
