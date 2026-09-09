"""TOTP (RFC 6238) generation and verification — ADR-0051.

Uses pyotp, a pure algorithmic implementation of the RFC with no I/O and
no framework dependency (no HTTP client, no database driver, nothing
that talks to an external service) — the same class of library
domain/otp.py's own docstring already treats as domain-layer-appropriate
(hashlib/hmac there; pyotp here), not the "web/ORM/messaging/frontend/
cloud" infrastructure packages/domain/README.md's technology-
independence rule actually excludes.
"""

from __future__ import annotations

import pyotp

_ISSUER = "VISTAAR"


def generate_totp_secret() -> str:
    """A fresh, random base32 secret — pyotp's own CSPRNG-backed
    generator (wraps `secrets`, not `random`)."""
    return pyotp.random_base32()


def totp_provisioning_uri(*, secret: str, account_label: str) -> str:
    """The `otpauth://` URI an authenticator app's QR scanner expects —
    account_label is shown in the app next to the VISTAAR issuer name,
    so an admin enrolling more than one VISTAAR-issued credential (there
    is only ever one per account today, but the app itself doesn't know
    that) can tell them apart. No PII beyond what the admin already sees
    in their own app (their phone number, the same identifier used
    throughout the rest of this codebase)."""
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=account_label, issuer_name=_ISSUER
    )


def verify_totp_code(*, secret: str, code: str) -> bool:
    """Accepts the current 30-second window plus one window of clock
    drift on either side (`valid_window=1`, pyotp's own built-in
    tolerance) — a phone's clock a few seconds off from the server's
    should not lock an admin out."""
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)
