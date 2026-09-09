"""Sarthi Wallet Recharge — payment gateway abstraction (ADR-0060,
2026-09-02).

Mirrors modules/identity/sms.py's and modules/notification/push.py's own
dev/real provider split exactly: a `WalletRechargeGateway` Protocol
(ports.py-style interface, kept in this file rather than ports.py since
this is an *external* gateway boundary, not an internal repository —
same distinction sms.py/push.py already draw by living outside their
module's own ports.py), a `DevWalletRechargeGateway` (always available,
no credential, nothing real happens) as the default, and
`RazorpayWalletRechargeGateway` as the first real implementation,
selected via `WALLET_RECHARGE_PROVIDER=razorpay`.

Razorpay is a TEST/DEVELOPMENT gateway only — the eventual production
gateway is SBI, still unselected. Every method on the Protocol below is
named around what a wallet recharge actually needs (create an order,
verify a completed payment, verify a webhook, credit the wallet,
reconcile) rather than around Razorpay's own vocabulary, specifically so
swapping in an SBI implementation later only means writing a new class
against this same Protocol — `modules/wallet/router.py` (the only
caller) never sees a Razorpay-specific type or field name. See ADR-0060
§4 for the exact list of what changes when SBI replaces this.

CAVEAT (same class of flag ADR-0031 gave MSG91's OTP integration, and
ADR-0052 gave the FCM push provider before a real project existed):
`RazorpayWalletRechargeGateway` is built from Razorpay's own publicly
documented Orders API and HMAC-SHA256 signature scheme, not verified
against a live Razorpay account in this environment — a test Key ID was
supplied, but not the Key Secret a real API call or signature
verification needs, so no live call has been made. The shape (Basic
Auth key_id:key_secret, POST /v1/orders, HMAC-SHA256 order/payment-id
signature verification, X-Razorpay-Signature webhook verification) is
Razorpay's own documented standard, but should be confirmed against a
real test account before relying on it.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import httpx

from core.config import settings

logger = logging.getLogger("vistaar.wallet.payment_gateway")

_RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"
_RAZORPAY_TIMEOUT_SECONDS = 15.0


@dataclass(slots=True)
class RechargeOrder:
    """Everything the mobile app's checkout step needs — provider-
    agnostic field names, even though only one provider exists today.
    `client_key` is the gateway's *public* identifier (Razorpay's
    key_id) — safe to send to the client, unlike the secret used to
    create this order server-side."""

    order_id: str
    amount: Decimal
    currency: str
    client_key: str


class PaymentGatewayError(Exception):
    """Raised when the gateway rejects an order-creation call, or a
    payment/webhook fails verification. Same shape as
    modules.identity.sms.Msg91DeliveryError — a clean domain-ish error
    instead of a raw httpx/provider exception reaching the caller."""


class WalletRechargeGateway(Protocol):
    async def create_order(
        self, *, driver_id: uuid.UUID, amount: Decimal
    ) -> RechargeOrder:
        """Creates a pending order for `amount` (INR) against this
        driver — no wallet effect yet; only a successfully *verified*
        payment (verify_payment()/verify_webhook_event(), below) ever
        credits the wallet."""
        ...

    async def verify_payment(
        self, *, order_id: str, payment_id: str, signature: str
    ) -> Decimal | None:
        """Server-side verification of a payment the mobile app's
        checkout step reports as complete — never trust the client's
        own "success" callback alone (security.md §27's "a client-side
        success screen is not proof of payment," reused here for the
        one gateway this codebase actually has), and never trust a
        client-supplied amount either: the verified amount is read back
        from the gateway's own record of the payment, not from the
        request that reported it. Returns the verified amount (INR) if
        the payment is genuinely captured, `None` for a merely-failed/
        invalid-signature payment (a normal "no" answer, not an
        exception) — raises only for a genuine gateway/network error."""
        ...

    def verify_webhook_signature(self, *, payload: bytes, signature: str) -> bool:
        """Verifies a webhook's authenticity before its body is trusted
        at all. Synchronous — pure HMAC computation, no network call."""
        ...

    def parse_captured_payment(
        self, payload: dict[str, object]
    ) -> tuple[uuid.UUID, str, Decimal] | None:
        """Extracts (driver_id, payment_id, amount) from a webhook
        payload already confirmed authentic, if and only if it
        represents a successfully captured payment — None for any other
        event type (this codebase only acts on capture events; a
        failure/refund webhook is logged, not acted on, matching "handle
        failed/cancelled/duplicate/uncertain states safely" without
        inventing a refund/dispute flow nothing asked for)."""
        ...


class DevWalletRechargeGateway:
    """Local-development adapter — mirrors DevConsoleSmsProvider/
    DevConsolePushProvider's own "always available, no credential,
    nothing real happens" treatment exactly. create_order() returns a
    syntactically valid order with a fake id; nothing is ever actually
    verified as paid (verify_payment() always returns None) — a fake
    "yes" here would be worse than unavailable, the same reasoning
    DevConsoleSmsProvider's own module docstring already gives for OTP.
    Must not be used in production."""

    async def create_order(
        self, *, driver_id: uuid.UUID, amount: Decimal
    ) -> RechargeOrder:
        logger.info(
            "DEV WALLET RECHARGE GATEWAY (no real provider configured): "
            "would create a ₹%s order for driver=%s",
            amount,
            driver_id,
        )
        return RechargeOrder(
            order_id=f"dev_order_{uuid.uuid4()}",
            amount=amount,
            currency="INR",
            client_key="dev_no_real_key",
        )

    async def verify_payment(
        self, *, order_id: str, payment_id: str, signature: str
    ) -> Decimal | None:
        logger.info(
            "DEV WALLET RECHARGE GATEWAY: verify_payment always returns "
            "None (order=%s, payment=%s) — no real provider configured.",
            order_id,
            payment_id,
        )
        return None

    def verify_webhook_signature(self, *, payload: bytes, signature: str) -> bool:
        return False

    def parse_captured_payment(
        self, payload: dict[str, object]
    ) -> tuple[uuid.UUID, str, Decimal] | None:
        return None


class RazorpayWalletRechargeGateway:
    def __init__(
        self,
        *,
        key_id: str,
        key_secret: str,
        webhook_secret: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret
        # transport is None in every real (non-test) construction path —
        # get_wallet_recharge_gateway() below never passes one. Tests
        # inject httpx.MockTransport, same convention
        # Msg91SmsProvider/FcmPushProvider already use.
        self._transport = transport

    async def create_order(
        self, *, driver_id: uuid.UUID, amount: Decimal
    ) -> RechargeOrder:
        # Razorpay's Orders API takes amount in the smallest currency
        # unit (paise for INR) — same "integer minor units, never
        # floating point" discipline security.md §55 already requires
        # everywhere else in this codebase.
        amount_paise = int((amount * 100).to_integral_value())
        try:
            async with httpx.AsyncClient(
                timeout=_RAZORPAY_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{_RAZORPAY_BASE_URL}/orders",
                    auth=(self._key_id, self._key_secret),
                    json={
                        "amount": amount_paise,
                        "currency": "INR",
                        # Echoed back on every webhook for this order —
                        # this is how parse_captured_payment() below
                        # recovers which driver a webhook is for,
                        # without a separate orders table.
                        "notes": {"driver_id": str(driver_id)},
                    },
                )
        except httpx.HTTPError as exc:
            logger.error("Razorpay create-order failed (network error): %s", exc)
            raise PaymentGatewayError(str(exc)) from exc

        if response.status_code >= 400:
            logger.error(
                "Razorpay create-order failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise PaymentGatewayError(
                f"Razorpay returned HTTP {response.status_code}: {response.text}"
            )

        body = response.json()
        order_id = body.get("id")
        if not order_id:
            raise PaymentGatewayError(f"Razorpay order response had no id: {body!r}")

        return RechargeOrder(
            order_id=str(order_id),
            amount=amount,
            currency="INR",
            client_key=self._key_id,
        )

    async def verify_payment(
        self, *, order_id: str, payment_id: str, signature: str
    ) -> Decimal | None:
        # Step 1: HMAC-SHA256(order_id|payment_id, key_secret) must
        # match the client-supplied signature — Razorpay's own
        # documented checkout-verification scheme.
        expected = hmac.new(
            self._key_secret.encode("utf-8"),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.warning(
                "Razorpay payment signature mismatch: order=%s payment=%s",
                order_id,
                payment_id,
            )
            return None

        # Step 2: confirm the payment's real status server-side too —
        # a matching signature alone is the documented minimum, but
        # querying the payment directly is the more defensive practice
        # this codebase's own "never trust the client alone" principle
        # (security.md §27) calls for.
        try:
            async with httpx.AsyncClient(
                timeout=_RAZORPAY_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{_RAZORPAY_BASE_URL}/payments/{payment_id}",
                    auth=(self._key_id, self._key_secret),
                )
        except httpx.HTTPError as exc:
            logger.error("Razorpay get-payment failed (network error): %s", exc)
            raise PaymentGatewayError(str(exc)) from exc

        if response.status_code >= 400:
            logger.error(
                "Razorpay get-payment failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise PaymentGatewayError(
                f"Razorpay returned HTTP {response.status_code}: {response.text}"
            )

        body = response.json()
        if body.get("status") != "captured":
            logger.warning(
                "Razorpay payment not captured: payment=%s status=%r",
                payment_id,
                body.get("status"),
            )
            return None
        amount_paise = body.get("amount")
        if amount_paise is None:
            raise PaymentGatewayError(
                f"Razorpay payment response had no amount: {body!r}"
            )
        # The verified amount comes from this response, never from the
        # client's own request — see this method's own doc comment.
        return Decimal(int(amount_paise)) / 100

    def verify_webhook_signature(self, *, payload: bytes, signature: str) -> bool:
        expected = hmac.new(
            self._webhook_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_captured_payment(
        self, payload: dict[str, object]
    ) -> tuple[uuid.UUID, str, Decimal] | None:
        # Razorpay's documented webhook envelope:
        # {"event": "payment.captured", "payload": {"payment": {"entity": {...}}}}
        if payload.get("event") != "payment.captured":
            return None
        try:
            entity = payload["payload"]["payment"]["entity"]  # type: ignore[index]
            payment_id = str(entity["id"])
            amount_paise = int(entity["amount"])
            driver_id = uuid.UUID(str(entity["notes"]["driver_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            logger.error("Razorpay webhook payload missing expected fields: %s", exc)
            return None
        return driver_id, payment_id, Decimal(amount_paise) / 100


def get_wallet_recharge_gateway() -> (
    DevWalletRechargeGateway | RazorpayWalletRechargeGateway
):
    """Factory for the configured gateway — mirrors
    modules.identity.sms.get_sms_provider()'s own shape exactly."""
    provider = settings.WALLET_RECHARGE_PROVIDER
    if provider == "dev":
        return DevWalletRechargeGateway()
    if provider == "razorpay":
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise ValueError(
                "WALLET_RECHARGE_PROVIDER=razorpay requires RAZORPAY_KEY_ID "
                "and RAZORPAY_KEY_SECRET to both be set."
            )
        return RazorpayWalletRechargeGateway(
            key_id=settings.RAZORPAY_KEY_ID,
            key_secret=settings.RAZORPAY_KEY_SECRET,
            webhook_secret=settings.RAZORPAY_WEBHOOK_SECRET,
        )
    raise NotImplementedError(
        f"WALLET_RECHARGE_PROVIDER={provider!r} is not implemented. Only "
        "'dev' and 'razorpay' exist — Razorpay is TEST/DEVELOPMENT only; "
        "the eventual production gateway (SBI) is a separate, still-"
        "unselected integration (ADR-0060 §5)."
    )
