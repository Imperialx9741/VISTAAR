"""Unit tests for modules.notification.push's real-provider adapter
(ADR-0052).

FcmPushProvider is exercised entirely against httpx.MockTransport — no
real network call, no real Firebase project needed (none is configured
anywhere in this environment; see the ADR's own caveat). A real RSA
keypair is generated per test (cryptography, already a transitive
dependency via pyjwt[crypto]) so jwt.encode(algorithm="RS256") has a
syntactically valid key to sign with — the mock transport never
verifies the resulting JWT's signature, only this codebase's own
encode step needs a real key.

Async send() calls are driven via asyncio.run() from ordinary sync test
functions, same convention as tests/test_identity_sms.py.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from modules.notification.push import (
    DevConsolePushProvider,
    FcmDeliveryError,
    FcmPushProvider,
    get_push_provider,
)


@pytest.fixture
def service_account_path(tmp_path: Path) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    account = {
        "client_email": "vistaar-test@example.iam.gserviceaccount.com",
        "private_key": private_pem,
        "token_uri": "https://oauth2.googleapis.com/token",
        "project_id": "vistaar-test",
    }
    path = tmp_path / "service-account.json"
    path.write_text(json.dumps(account))
    return str(path)


def _client(service_account_path: str, handler) -> FcmPushProvider:
    return FcmPushProvider(
        service_account_json_path=service_account_path,
        transport=httpx.MockTransport(handler),
    )


def test_send_success(service_account_path: str) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com" in str(request.url):
            captured["token_body"] = request.read().decode("utf-8")
            return httpx.Response(200, json={"access_token": "fake-access-token"})
        captured["send_url"] = str(request.url)
        captured["auth_header"] = request.headers.get("authorization")
        captured["send_body"] = json.loads(request.read())
        return httpx.Response(200, json={"name": "projects/x/messages/123"})

    provider = _client(service_account_path, handler)
    result = asyncio.run(provider.send("device-token-1", title="Hi", body="There"))

    assert result == "projects/x/messages/123"
    assert captured["auth_header"] == "Bearer fake-access-token"
    assert "vistaar-test/messages:send" in str(captured["send_url"])
    body = captured["send_body"]
    assert isinstance(body, dict)
    message = body["message"]
    assert isinstance(message, dict)
    assert message["token"] == "device-token-1"
    assert message["notification"] == {"title": "Hi", "body": "There"}
    assert "assertion=" in str(captured["token_body"])


def test_send_raises_when_token_exchange_fails(service_account_path: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid_grant")

    provider = _client(service_account_path, handler)

    with pytest.raises(FcmDeliveryError):
        asyncio.run(provider.send("device-token-1", title="Hi", body="There"))


def test_send_raises_when_fcm_send_fails(service_account_path: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com" in str(request.url):
            return httpx.Response(200, json={"access_token": "fake-access-token"})
        return httpx.Response(404, json={"error": {"message": "not registered"}})

    provider = _client(service_account_path, handler)

    with pytest.raises(FcmDeliveryError):
        asyncio.run(provider.send("device-token-1", title="Hi", body="There"))


def test_send_raises_when_token_response_has_no_access_token(
    service_account_path: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    provider = _client(service_account_path, handler)

    with pytest.raises(FcmDeliveryError):
        asyncio.run(provider.send("device-token-1", title="Hi", body="There"))


def test_dev_console_provider_does_not_raise() -> None:
    provider = DevConsolePushProvider()
    result = asyncio.run(provider.send("device-token-1", title="Hi", body="There"))
    assert result is None


def test_get_push_provider_defaults_to_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.config import settings

    monkeypatch.setattr(settings, "PUSH_PROVIDER", "dev")
    assert isinstance(get_push_provider(), DevConsolePushProvider)


def test_get_push_provider_raises_when_fcm_misconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.config import settings

    monkeypatch.setattr(settings, "PUSH_PROVIDER", "fcm")
    monkeypatch.setattr(settings, "FCM_SERVICE_ACCOUNT_JSON", "")

    with pytest.raises(ValueError, match="FCM_SERVICE_ACCOUNT_JSON"):
        get_push_provider()


def test_get_push_provider_returns_fcm_provider_when_configured(
    monkeypatch: pytest.MonkeyPatch, service_account_path: str
) -> None:
    """Fills a gap the other get_push_provider() tests left: dev-default
    and fcm-misconfigured were both covered, but nothing actually
    exercised the success path — PUSH_PROVIDER=fcm plus a real,
    loadable credentials file constructing a working FcmPushProvider
    from it (2026-09-01, once a real Firebase service-account credential
    existed to configure this against, kept outside this repo per the
    codebase's own secrets discipline; this test still uses the same
    synthetic tmp_path fixture as every other test in this file, never
    the real credential)."""
    from core.config import settings

    monkeypatch.setattr(settings, "PUSH_PROVIDER", "fcm")
    monkeypatch.setattr(settings, "FCM_SERVICE_ACCOUNT_JSON", service_account_path)

    provider = get_push_provider()

    assert isinstance(provider, FcmPushProvider)


def test_get_push_provider_raises_for_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.config import settings

    monkeypatch.setattr(settings, "PUSH_PROVIDER", "onesignal")

    with pytest.raises(NotImplementedError):
        get_push_provider()
