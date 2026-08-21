from collections.abc import AsyncGenerator

from redis.asyncio import Redis, from_url

from core.config import settings


def get_redis_client() -> Redis:
    """Create and return an async Redis client instance.

    Configured using settings.REDIS_URL.
    """
    return from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding an async Redis client with clean aclose() teardown.

    Yields:
        Redis: An active async Redis client instance.
    """
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()
