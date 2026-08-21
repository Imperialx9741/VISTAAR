import pytest
from aiokafka.admin import AIOKafkaAdminClient
from aiokafka.errors import (
    KafkaConnectionError,
    KafkaError,
    NoBrokersAvailable,
    NodeNotReadyError,
)

from core.config import settings
from core.kafka import check_kafka_connection, get_kafka_admin_client


def test_kafka_configuration() -> None:
    """Verify that Kafka configuration settings load properly."""
    assert settings.KAFKA_BOOTSTRAP_SERVERS is not None
    assert settings.KAFKA_BOOTSTRAP_SERVERS == "127.0.0.1:9092"


@pytest.mark.anyio
async def test_kafka_client_creation() -> None:
    """Verify get_kafka_admin_client creates an unstarted AIOKafkaAdminClient."""
    admin = get_kafka_admin_client()
    assert isinstance(admin, AIOKafkaAdminClient)


@pytest.mark.anyio
async def test_kafka_broker_connectivity() -> None:
    """Integration test to verify real Kafka broker connectivity and metadata retrieval.

    Skips ONLY when Kafka broker is genuinely unreachable (NoBrokersAvailable,
    KafkaConnectionError, OSError, TimeoutError). Unexpected errors fail the test.
    """
    try:
        res = await check_kafka_connection()
        assert res["status"] == "healthy"
        assert res["kafka"] == "connected"
    except (
        NoBrokersAvailable,
        KafkaConnectionError,
        NodeNotReadyError,
        OSError,
        TimeoutError,
    ) as e:
        pytest.skip(
            f"Kafka broker at {settings.KAFKA_BOOTSTRAP_SERVERS} is unreachable: {e}"
        )


@pytest.mark.anyio
async def test_kafka_client_lifecycle() -> None:
    """Verify admin client lifecycle completes cleanly and closes in finally block."""
    admin = get_kafka_admin_client()
    try:
        await admin.start()
        cluster_info = await admin.describe_cluster()
        assert cluster_info is not None
    except (
        NoBrokersAvailable,
        KafkaConnectionError,
        NodeNotReadyError,
        OSError,
        TimeoutError,
    ) as e:
        pytest.skip(f"Kafka lifecycle test skipped because broker is unreachable: {e}")
    except KafkaError as e:
        pytest.fail(f"Unexpected Kafka error occurred during lifecycle test: {e}")
    finally:
        await admin.close()
