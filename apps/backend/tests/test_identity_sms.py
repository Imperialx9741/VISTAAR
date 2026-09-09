"""Unit tests for modules.identity.sms's real-provider adapter (ADR-0031).

Msg91SmsProvider is exercised entirely against httpx.MockTransport — no
real network call, no real MSG91 account needed (none is configured
anywhere in this environment; see the ADR's own caveat). DevConsoleSmsProvider
and get_sms_provider()'s dispatch logic are also covered here, not
elsewhere, since no test file previously existed for this module.

Async send_otp() calls are driven via asyncio.run() from ordinary sync
test functions — same convention this codebase's other async-call sites
already use (e.g. tests/test_ride_lifecycle_api.py's Redis cleanup),
since no pytest-asyncio plugin is configured for this suite.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from modules.identity.sms import (
    DevConsoleSmsProvider,
    Msg91DeliveryError,
    Msg91SmsProvider,
    get_sms_provider,
    identity_settings,
)


def _client(handler, *, notification_template_id: str = "") -> Msg91SmsProvider:
    return Msg91SmsProvider(
        auth_key="test-authkey",
        template_id="test-template",
        notification_template_id=notification_template_id,
        transport=httpx.MockTransport(handler),
    )


def test_send_otp_success() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authkey"] = request.headers.get("authkey")
        return httpx.Response(200, json={"type": "success", "message": "OTP sent"})

    provider = _client(handler)
    asyncio.run(provider.send_otp("+919876543210", "123456"))

    assert captured["authkey"] == "test-authkey"
    url = str(captured["url"])
    assert "control.msg91.com/api/v5/otp" in url
    assert "template_id=test-template" in url
    # The leading "+" must be stripped for MSG91's `mobile` param.
    assert "mobile=919876543210" in url
    assert "otp=123456" in url


def test_send_otp_strips_leading_plus_from_phone_number() -> None:
    captured_url: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_url["url"] = str(request.url)
        return httpx.Response(200, json={"type": "success"})

    provider = _client(handler)
    asyncio.run(provider.send_otp("+15551234567", "000000"))

    assert "mobile=15551234567" in captured_url["url"]
    assert "mobile=%2B15551234567" not in captured_url["url"]


def test_send_otp_raises_on_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid authkey")

    provider = _client(handler)
    with pytest.raises(Msg91DeliveryError):
        asyncio.run(provider.send_otp("+919876543210", "123456"))


def test_send_otp_raises_on_non_success_body_despite_200() -> None:
    """MSG91 is known to return HTTP 200 with an in-body error for some
    failure classes (e.g. invalid template_id) — must not be treated as
    delivered."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"type": "error", "message": "invalid mobile"})

    provider = _client(handler)
    with pytest.raises(Msg91DeliveryError):
        asyncio.run(provider.send_otp("+919876543210", "123456"))


def test_send_otp_raises_on_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = _client(handler)
    with pytest.raises(Msg91DeliveryError):
        asyncio.run(provider.send_otp("+919876543210", "123456"))


def test_dev_console_provider_does_not_raise() -> None:
    # Purely logs — no assertion beyond "does not raise" is meaningful
    # here (security.md §5: never returned to the client either way).
    asyncio.run(DevConsoleSmsProvider().send_otp("+919876543210", "123456"))


# --- send_message() (ADR-0034 — Notification Domain Foundation) ------------


def test_send_message_success() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authkey"] = request.headers.get("authkey")
        captured["body"] = request.read()
        return httpx.Response(
            200, json={"type": "success", "request_id": "req-abc-123"}
        )

    provider = _client(handler, notification_template_id="notif-template")
    reference = asyncio.run(
        provider.send_message("+919876543210", "Your ride has been accepted.")
    )

    assert reference == "req-abc-123"
    assert captured["authkey"] == "test-authkey"
    assert "control.msg91.com/api/v5/flow/" in str(captured["url"])
    body = captured["body"]
    assert isinstance(body, bytes)
    assert b"notif-template" in body
    assert b"919876543210" in body
    assert b"Your ride has been accepted." in body


def test_send_message_raises_when_notification_template_not_configured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call MSG91 with no template configured")

    provider = _client(handler)  # notification_template_id="" (default)
    with pytest.raises(Msg91DeliveryError):
        asyncio.run(provider.send_message("+919876543210", "hello"))


def test_send_message_raises_on_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid authkey")

    provider = _client(handler, notification_template_id="notif-template")
    with pytest.raises(Msg91DeliveryError):
        asyncio.run(provider.send_message("+919876543210", "hello"))


def test_send_message_raises_on_non_success_body_despite_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"type": "error", "message": "bad template"})

    provider = _client(handler, notification_template_id="notif-template")
    with pytest.raises(Msg91DeliveryError):
        asyncio.run(provider.send_message("+919876543210", "hello"))


def test_send_message_raises_on_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = _client(handler, notification_template_id="notif-template")
    with pytest.raises(Msg91DeliveryError):
        asyncio.run(provider.send_message("+919876543210", "hello"))


def test_dev_console_provider_send_message_does_not_raise() -> None:
    reference = asyncio.run(
        DevConsoleSmsProvider().send_message("+919876543210", "hello")
    )
    assert reference is None


def test_get_sms_provider_defaults_to_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_settings, "sms_provider", "dev")
    assert isinstance(get_sms_provider(), DevConsoleSmsProvider)


def test_get_sms_provider_returns_msg91_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity_settings, "sms_provider", "msg91")
    monkeypatch.setattr(identity_settings, "msg91_auth_key", "key")
    monkeypatch.setattr(identity_settings, "msg91_template_id", "template")
    assert isinstance(get_sms_provider(), Msg91SmsProvider)


def test_get_sms_provider_raises_when_msg91_misconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity_settings, "sms_provider", "msg91")
    monkeypatch.setattr(identity_settings, "msg91_auth_key", "")
    monkeypatch.setattr(identity_settings, "msg91_template_id", "")
    with pytest.raises(ValueError):
        get_sms_provider()


def test_get_sms_provider_raises_for_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity_settings, "sms_provider", "twilio")
    with pytest.raises(NotImplementedError):
        get_sms_provider()
