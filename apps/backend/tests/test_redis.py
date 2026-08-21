import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from core.config import settings
from core.redis import get_redis, get_redis_client


def test_redis_configuration() -> None:
    """Verify that Redis configuration settings load properly."""
    assert settings.REDIS_URL is not None
    assert settings.REDIS_URL.startswith("redis://") or settings.REDIS_URL.startswith(
        "rediss://"
    )


def test_redis_client_creation() -> None:
    """Verify that get_redis_client returns a valid async Redis client instance."""
    client = get_redis_client()
    assert client is not None


@pytest.mark.anyio
async def test_redis_ping_connection() -> None:
    """Integration test to verify real Redis PING communication.

    Skips ONLY when Redis is genuinely unreachable (connection refused/timeout).
    Command failures or other client errors fail the test.
    """
    client = get_redis_client()
    try:
        pong = await client.ping()
        assert pong is True
    except (RedisConnectionError, RedisTimeoutError, OSError) as e:
        pytest.skip(f"Redis server at {settings.REDIS_URL} is unreachable: {e}")
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_redis_dependency_lifecycle() -> None:
    """Verify get_redis async generator lifecycle and clean aclose() teardown."""
    redis_gen = get_redis()
    try:
        client = await anext(redis_gen)
        assert client is not None
        try:
            pong = await client.ping()
            assert pong is True
        except (RedisConnectionError, RedisTimeoutError, OSError) as e:
            pytest.skip(f"Redis is unreachable during lifecycle test: {e}")
    finally:
        # Trigger generator cleanup (finally block in get_redis)
        with pytest.raises(StopAsyncIteration):
            await anext(redis_gen)
