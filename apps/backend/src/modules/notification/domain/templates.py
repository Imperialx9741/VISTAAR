"""SMS message templates, keyed by `template_key`.

ADR-0034 Decision 4: this is flat, static placeholder copy — no
document anywhere specifies actual customer-facing wording (domain-
design.md §20.2 only says the domain "owns... templates", not what they
say), and no variable-substitution/localization system exists (a future
task's job, not this one's). Treat every string below as illustrative,
not approved copy — revising it is a plain code change, no schema/API
impact, unlike the rates/thresholds this session has otherwise been
careful to get owner sign-off on.

Real MSG91 delivery in production additionally needs each of these
pre-registered as an Indian-telecom DLT template (a regulatory
requirement for commercial SMS, distinct from and in addition to
whatever wording is used here) — no DLT registration exists in this
environment, the same "wired, not verified against a live account"
caveat ADR-0031 already gave MSG91's OTP integration.
"""

from __future__ import annotations

from modules.notification.domain.errors import UnknownTemplateError

SMS_TEMPLATES: dict[str, str] = {
    "RIDE_ACCEPTED": (
        "Your VISTAAR ride has been accepted. Your driver is on the way "
        "to the pickup point."
    ),
    "RIDE_ARRIVED": (
        "Your VISTAAR driver has arrived at the pickup point. Please "
        "share your OTP with the driver to start the ride."
    ),
    # ADR-0050 — sent to the internal safety/call-center team (every
    # Super Admin + every admin with SAFETY MANAGE access), not a rider.
    "SOS_TRIGGERED": (
        "VISTAAR SOS ALERT: a new incident has been triggered. Open the "
        "Admin Console's Safety/SOS queue immediately."
    ),
    # Sarthi Wallet Low-Balance Rule (ADR-0058, 2026-09-02, owner
    # decision) — sent once, the moment a platform-fee debit brings the
    # driver's wallet balance to ₹20 or below (matching_service's own
    # accept-offer endpoint).
    "WALLET_LOW_BALANCE": (
        "Your VISTAAR wallet balance is low (₹20 or below). You can "
        "accept one more ride, but you'll need to recharge your wallet "
        "before accepting another."
    ),
}


def render_sms(template_key: str) -> str:
    try:
        return SMS_TEMPLATES[template_key]
    except KeyError:
        raise UnknownTemplateError(
            f"No SMS template registered for template_key={template_key!r}."
        ) from None
