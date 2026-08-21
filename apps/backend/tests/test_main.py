import pytest
from fastapi.testclient import TestClient


def test_read_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to VISTAAR Backend API"}


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_db_health_check(client: TestClient) -> None:
    response = client.get("/health/db")
    if response.status_code == 503:
        detail = response.json().get("detail", "").lower()
        unreachable_phrases = [
            "connection refused",
            "could not connect to server",
            "timeout expired",
            "is the server running",
            "does not exist",
            "failed",
        ]
        if any(phrase in detail for phrase in unreachable_phrases):
            pytest.skip(f"Database is offline or unreachable: {detail}")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}


def test_redis_health_check(client: TestClient) -> None:
    response = client.get("/health/redis")
    if response.status_code == 503:
        detail = response.json().get("detail", "").lower()
        unreachable_phrases = [
            "connection refused",
            "could not connect",
            "timeout",
            "failed",
            "error",
        ]
        if any(phrase in detail for phrase in unreachable_phrases):
            pytest.skip(f"Redis is offline or unreachable: {detail}")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "redis": "connected"}


def test_kafka_health_check(client: TestClient) -> None:
    response = client.get("/health/kafka")
    if response.status_code == 503:
        detail = response.json().get("detail", "").lower()
        unreachable_phrases = [
            "connection refused",
            "could not connect",
            "no brokers available",
            "timeout",
            "failed",
            "error",
        ]
        if any(phrase in detail for phrase in unreachable_phrases):
            pytest.skip(f"Kafka is offline or unreachable: {detail}")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "kafka": "connected"}
