from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sentry_sdk.types import Event

from main import _scrub_sensitive_sentry_data


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


class TestScrubSensitiveSentryData:
    """Security review finding, 2026-09-02 — see _scrub_sensitive_sentry_data's
    own doc comment in main.py."""

    def test_authorization_header_is_redacted(self) -> None:
        event = cast(
            Event,
            {"request": {"headers": {"Authorization": "Bearer real-token-value"}}},
        )

        scrubbed = cast(dict[str, Any], _scrub_sensitive_sentry_data(event, {}))

        assert scrubbed is not None
        assert scrubbed["request"]["headers"]["Authorization"] == "[Filtered]"

    def test_cookie_header_is_redacted_case_insensitively(self) -> None:
        event = cast(
            Event,
            {"request": {"headers": {"cookie": "session=real-session-value"}}},
        )

        scrubbed = cast(dict[str, Any], _scrub_sensitive_sentry_data(event, {}))

        assert scrubbed is not None
        assert scrubbed["request"]["headers"]["cookie"] == "[Filtered]"

    def test_other_headers_are_left_untouched(self) -> None:
        event = cast(Event, {"request": {"headers": {"X-Request-ID": "req-123"}}})

        scrubbed = cast(dict[str, Any], _scrub_sensitive_sentry_data(event, {}))

        assert scrubbed is not None
        assert scrubbed["request"]["headers"]["X-Request-ID"] == "req-123"

    def test_event_with_no_request_or_headers_does_not_crash(self) -> None:
        assert _scrub_sensitive_sentry_data({}, {}) == {}
        assert _scrub_sensitive_sentry_data({"request": {}}, {}) == {"request": {}}
