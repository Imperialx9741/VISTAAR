"""ADR-0036: SecurityHeadersMiddleware applies a fixed header set to
every response, with CSP specifically excluded on the interactive-docs
paths — see shared/security_headers.py's own module docstring for why.
"""

from fastapi.testclient import TestClient


def test_health_endpoint_carries_the_fixed_headers(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert (
        response.headers["Strict-Transport-Security"]
        == "max-age=63072000; includeSubDomains"
    )


def test_health_endpoint_carries_a_strict_csp(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'"
    )


def test_root_endpoint_also_carries_the_headers(client: TestClient) -> None:
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in response.headers


def test_docs_path_is_exempt_from_csp_but_keeps_the_other_headers(
    client: TestClient,
) -> None:
    response = client.get("/docs")
    assert "Content-Security-Policy" not in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_redoc_path_is_exempt_from_csp(client: TestClient) -> None:
    response = client.get("/redoc")
    assert "Content-Security-Policy" not in response.headers


def test_openapi_json_path_is_exempt_from_csp(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert "Content-Security-Policy" not in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_a_404_response_still_carries_the_headers(client: TestClient) -> None:
    response = client.get("/this-path-does-not-exist")
    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'"
    )
