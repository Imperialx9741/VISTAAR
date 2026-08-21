from typing import Any

from aiokafka.admin import AIOKafkaAdminClient

from core.config import settings


def get_kafka_admin_client() -> AIOKafkaAdminClient:
    """Create and return an unstarted AIOKafkaAdminClient instance.

    Configured using settings.KAFKA_BOOTSTRAP_SERVERS.
    Does not create a persistent global connection or background thread.
    """
    return AIOKafkaAdminClient(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    )


async def check_kafka_connection() -> dict[str, Any]:
    """Execute a complete Kafka admin lifecycle metadata query.

    1. Instantiates the admin client.
    2. Starts the admin client connection.
    3. Queries describe_cluster() for broker metadata.
    4. Guarantees cleanup via a finally block (calling admin.close()).

    Returns:
        dict[str, Any]: Cluster metadata status information.
    """
    admin = get_kafka_admin_client()
    await admin.start()
    try:
        cluster_info = await admin.describe_cluster()
        return {
            "status": "healthy",
            "kafka": "connected",
            "cluster_info": cluster_info,
        }
    finally:
        await admin.close()
