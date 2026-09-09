"""Unit tests for Sarthi Wallet Recharge's payment gateway abstraction
(ADR-0060).

RazorpayWalletRechargeGateway is exercised entirely against
httpx.MockTransport — no real network call, no real Razorpay account
needed (a test Key ID exists in this environment, but not the Key
Secret a real authenticated call needs — see payment_gateway.py's own
module docstring for this same caveat).

Async provider calls are driven via asyncio.run() from ordinary sync
test functions — same convention tests/test_notification_push.py
already established (this codebase's pytest setup has no native
async-test-function support).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from decimal import Decimal

import httpx
import pytest

from modules.wallet.payment_gateway import (
    DevWalletRechargeGateway,
    PaymentGatewayError,
    RazorpayWalletRechargeGateway,
    get_wallet_recharge_gateway,
)

_KEY_ID = "rzp_test_fake_key_id"
_KEY_SECRET = "fake_key_secret"
_WEBHOOK_SECRET = "fake_webhook_secret"


def _gateway(handler) -> RazorpayWalletRechargeGateway:
    return RazorpayWalletRechargeGateway(
        key_id=_KEY_ID,
        key_secret=_KEY_SECRET,
        webhook_secret=_WEBHOOK_SECRET,
        transport=httpx.MockTransport(handler),
    )


def _sign(order_id: str, payment_id: str) -> str:
    return hmac.new(
        _KEY_SECRET.encode("utf-8"),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def test_dev_gateway_create_order_returns_a_syntactically_valid_order() -> None:
    gateway = DevWalletRechargeGateway()
    order = asyncio.run(
        gateway.create_order(driver_id=uuid.uuid4(), amount=Decimal("500.00"))
    )
    assert order.amount == Decimal("500.00")
    assert order.currency == "INR"
    assert order.order_id.startswith("dev_order_")


def test_dev_gateway_verify_payment_always_returns_none() -> None:
    gateway = DevWalletRechargeGateway()
    result = asyncio.run(
        gateway.verify_payment(
            order_id="order-1", payment_id="pay-1", signature="whatever"
        )
    )
    assert result is None


def test_dev_gateway_verify_webhook_signature_always_returns_false() -> None:
    gateway = DevWalletRechargeGateway()
    assert gateway.verify_webhook_signature(payload=b"{}", signature="x") is False


def test_dev_gateway_parse_captured_payment_always_returns_none() -> None:
    gateway = DevWalletRechargeGateway()
    assert gateway.parse_captured_payment({"event": "payment.captured"}) is None


def test_create_order_sends_amount_in_paise_with_driver_id_in_notes() -> None:
    captured: dict[str, object] = {}
    driver_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200, json={"id": "order_abc123", "amount": 50000, "status": "created"}
        )

    gateway = _gateway(handler)
    order = asyncio.run(
        gateway.create_order(driver_id=driver_id, amount=Decimal("500"))
    )

    assert order.order_id == "order_abc123"
    assert order.amount == Decimal("500")
    assert order.client_key == _KEY_ID
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["amount"] == 50000
    assert body["currency"] == "INR"
    assert body["notes"] == {"driver_id": str(driver_id)}
    assert captured["auth"] is not None  # Basic Auth header present


def test_create_order_raises_on_gateway_error_response() -> None:
    gateway = _gateway(
        lambda _: httpx.Response(401, json={"error": {"description": "bad key"}})
    )
    with pytest.raises(PaymentGatewayError):
        asyncio.run(gateway.create_order(driver_id=uuid.uuid4(), amount=Decimal("500")))


def test_create_order_raises_when_response_has_no_id() -> None:
    gateway = _gateway(lambda _: httpx.Response(200, json={"status": "created"}))
    with pytest.raises(PaymentGatewayError):
        asyncio.run(gateway.create_order(driver_id=uuid.uuid4(), amount=Decimal("500")))


def test_verify_payment_returns_the_verified_amount_when_captured() -> None:
    gateway = _gateway(
        lambda _: httpx.Response(
            200, json={"id": "pay_1", "amount": 50000, "status": "captured"}
        )
    )
    signature = _sign("order_1", "pay_1")

    result = asyncio.run(
        gateway.verify_payment(
            order_id="order_1", payment_id="pay_1", signature=signature
        )
    )

    assert result == Decimal("500")


def test_verify_payment_returns_none_on_signature_mismatch() -> None:
    gateway = _gateway(
        lambda _: httpx.Response(200, json={"amount": 50000, "status": "captured"})
    )

    result = asyncio.run(
        gateway.verify_payment(
            order_id="order_1", payment_id="pay_1", signature="wrong-signature"
        )
    )

    assert result is None


def test_verify_payment_never_trusts_a_client_supplied_amount() -> None:
    """The gateway's own response amount (₹500) is what's returned, not
    anything the caller passed in — verify_payment() doesn't even
    accept an amount parameter, by design."""
    gateway = _gateway(
        lambda _: httpx.Response(
            200, json={"id": "pay_1", "amount": 50000, "status": "captured"}
        )
    )
    signature = _sign("order_1", "pay_1")

    result = asyncio.run(
        gateway.verify_payment(
            order_id="order_1", payment_id="pay_1", signature=signature
        )
    )

    assert result == Decimal("500")  # from the response, not guessed


def test_verify_payment_returns_none_when_not_captured() -> None:
    gateway = _gateway(
        lambda _: httpx.Response(
            200, json={"id": "pay_1", "amount": 50000, "status": "failed"}
        )
    )
    signature = _sign("order_1", "pay_1")

    result = asyncio.run(
        gateway.verify_payment(
            order_id="order_1", payment_id="pay_1", signature=signature
        )
    )

    assert result is None


def test_verify_payment_raises_on_gateway_network_error_response() -> None:
    gateway = _gateway(lambda _: httpx.Response(500, text="oops"))
    signature = _sign("order_1", "pay_1")
    with pytest.raises(PaymentGatewayError):
        asyncio.run(
            gateway.verify_payment(
                order_id="order_1", payment_id="pay_1", signature=signature
            )
        )


def test_verify_webhook_signature_accepts_a_correctly_signed_payload() -> None:
    gateway = _gateway(lambda _: httpx.Response(200))
    payload = b'{"event": "payment.captured"}'
    signature = hmac.new(
        _WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()

    assert gateway.verify_webhook_signature(payload=payload, signature=signature)


def test_verify_webhook_signature_rejects_a_tampered_payload() -> None:
    gateway = _gateway(lambda _: httpx.Response(200))
    real_payload = b'{"event": "payment.captured"}'
    signature = hmac.new(
        _WEBHOOK_SECRET.encode("utf-8"), real_payload, hashlib.sha256
    ).hexdigest()

    tampered = b'{"event": "payment.captured", "extra": "injected"}'
    assert not gateway.verify_webhook_signature(payload=tampered, signature=signature)


def test_parse_captured_payment_extracts_driver_id_payment_id_and_amount() -> None:
    gateway = _gateway(lambda _: httpx.Response(200))
    driver_id = uuid.uuid4()
    payload: dict[str, object] = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_xyz",
                    "amount": 50000,
                    "notes": {"driver_id": str(driver_id)},
                }
            }
        },
    }

    result = gateway.parse_captured_payment(payload)

    assert result == (driver_id, "pay_xyz", Decimal("500"))


def test_parse_captured_payment_ignores_non_capture_events() -> None:
    gateway = _gateway(lambda _: httpx.Response(200))
    payload: dict[str, object] = {"event": "payment.failed", "payload": {}}
    assert gateway.parse_captured_payment(payload) is None


def test_parse_captured_payment_returns_none_for_malformed_payload() -> None:
    gateway = _gateway(lambda _: httpx.Response(200))
    payload: dict[str, object] = {"event": "payment.captured", "payload": {}}
    assert gateway.parse_captured_payment(payload) is None


def test_get_wallet_recharge_gateway_defaults_to_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.config import settings

    monkeypatch.setattr(settings, "WALLET_RECHARGE_PROVIDER", "dev")
    assert isinstance(get_wallet_recharge_gateway(), DevWalletRechargeGateway)


def test_get_wallet_recharge_gateway_raises_when_razorpay_misconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.config import settings

    monkeypatch.setattr(settings, "WALLET_RECHARGE_PROVIDER", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "")

    with pytest.raises(ValueError, match="RAZORPAY_KEY_ID"):
        get_wallet_recharge_gateway()


def test_get_wallet_recharge_gateway_returns_razorpay_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.config import settings

    monkeypatch.setattr(settings, "WALLET_RECHARGE_PROVIDER", "razorpay")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")

    gateway = get_wallet_recharge_gateway()

    assert isinstance(gateway, RazorpayWalletRechargeGateway)


def test_get_wallet_recharge_gateway_raises_for_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.config import settings

    monkeypatch.setattr(settings, "WALLET_RECHARGE_PROVIDER", "stripe")

    with pytest.raises(NotImplementedError):
        get_wallet_recharge_gateway()
