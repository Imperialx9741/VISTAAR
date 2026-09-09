"""OTP generation and hash verification.

Uses only the Python standard library (``secrets``, ``hmac``, ``hashlib``)
so this stays in the pure domain layer — these are language primitives,
not the kind of web/ORM/messaging/frontend/cloud dependency
packages/domain/README.md's technology-independence rule excludes.

Security properties (per docs/08-security/security.md §4-5):
- Secure random generation: ``secrets.randbelow`` (CSPRNG), not ``random``.
- Never stored in plaintext where avoidable: only an HMAC-SHA256 digest of
  the OTP is ever persisted (see modules/identity/domain/entities.py's
  OtpChallenge.otp_hash / NewOtpChallenge.plaintext_otp docstring).
- One-time use / invalidate-on-verify is enforced by the application layer
  (service.py), which transitions OtpChallengeStatus to VERIFIED
  immediately on a successful check.
- Constant-time comparison (``hmac.compare_digest``) to avoid timing
  side-channels on OTP verification.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_OTP_LENGTH = 6  # 6 digits: standard OTP length; not a business-rule value.


def generate_numeric_otp(length: int = _OTP_LENGTH) -> str:
    """Generate a cryptographically secure numeric OTP of ``length`` digits."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def hash_otp(otp: str, *, pepper: str) -> str:
    """HMAC-SHA256 the OTP with a server-side secret ("pepper").

    HMAC (rather than a plain SHA-256 digest) is used so that knowledge of
    the hash alone is useless without the server-side secret, which is
    appropriate for a short numeric space (10^6 possibilities) where a
    plain fast hash would otherwise be brute-forceable offline if the
    database were ever exposed.
    """
    return hmac.new(
        pepper.encode("utf-8"), otp.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_otp(otp: str, *, pepper: str, expected_hash: str) -> bool:
    """Constant-time check that ``otp`` hashes to ``expected_hash``."""
    return hmac.compare_digest(hash_otp(otp, pepper=pepper), expected_hash)
