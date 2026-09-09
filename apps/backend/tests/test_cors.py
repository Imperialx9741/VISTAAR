"""CORS (2026-08-29, admin-web-implementation-plan.md §6) — the Admin
Web frontend calls this API directly from the browser; without
CORSMiddleware, every one of those cross-origin requests is rejected
regardless of how correct the backend's own response is.

`client` fixture (conftest.py) builds its TestClient against the real
`app`, which reads `core.config.settings.CORS_ALLOWED_ORIGINS` at
import time — these tests rely on the test environment's default
("http://localhost:3000", core/config.py's own fallback) rather than
overriding it, same as test_security_headers.py's own reliance on
SecurityHeadersMiddleware's fixed behavior.
"""

from fastapi.testclient import TestClient


def test_allowed_origin_gets_the_cors_header(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_disallowed_origin_gets_no_cors_header(client: TestClient) -> None:
    """The request itself still succeeds (CORS is enforced by the
    browser reading the response header, not the server refusing to
    respond) — but no Access-Control-Allow-Origin header is present,
    so a real browser would block the calling page from reading it."""
    response = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers


def test_preflight_request_is_answered_for_an_allowed_origin(
    client: TestClient,
) -> None:
    response = client.options(
        "/api/v1/admin/rides",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_cors_headers_still_present_alongside_security_headers(
    client: TestClient,
) -> None:
    """CORSMiddleware must wrap SecurityHeadersMiddleware (added first,
    per main.py's own comment on the ordering), so both header sets
    appear on the same response."""
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
