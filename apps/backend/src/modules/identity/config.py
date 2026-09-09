"""Identity module configuration.

IMPORTANT — every value below is an engineering/security configuration
choice, not a business-rule decision. docs/08-security/security.md §89
("Open Security Configuration") explicitly classifies "Exact OTP expiry",
"Exact API rate limits", "JWT/access-token lifetime", and "Refresh-token
lifetime" as "implementation/configuration choices rather than unresolved
business rules" that "should be finalized during infrastructure/security
implementation without changing the approved VISTAAR business model."
That is the authority under which this file sets working defaults — this
is a materially different situation from a business value like the fare
formula or GPS radius, which docs/01-product/PRD.md §62 and
docs/02-business/business-rules.md §43 explicitly forbid engineering from
inventing.

Every value is overridable via environment variable and defaults to
something reasonable for local development. Production deployments should
review and, where appropriate, override these.
"""

from __future__ import annotations

import os

from core.config import settings as core_settings


class IdentitySettings:
    def __init__(self) -> None:
        # --- JWT access tokens ---------------------------------------
        # Sourced from core.config.settings (single source of truth for
        # JWT_SECRET/JWT_ALGORITHM/JWT_ACCESS_TOKEN_EXPIRE_MINUTES, which
        # already existed in .env.example from Phase 1/Task 7 and are now
        # wired into core/config.py by this task) rather than re-reading
        # the same environment variables a second time here.
        self.jwt_secret: str = core_settings.JWT_SECRET
        self.jwt_algorithm: str = core_settings.JWT_ALGORITHM
        self.jwt_access_token_expire_minutes: int = (
            core_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

        # --- OTP ---------------------------------------------------
        # 300s (5 min) matches the "expires_in": 300 example already shown
        # in docs/05-api/api-contracts.md §6 — reusing the documented
        # example rather than picking an unrelated number, while treating
        # it as configuration per security.md §89, not as if that example
        # were itself an approved business rule.
        self.otp_length: int = int(os.getenv("OTP_LENGTH", "6"))
        self.otp_expiry_seconds: int = int(os.getenv("OTP_EXPIRY_SECONDS", "300"))
        self.otp_max_verify_attempts: int = int(
            os.getenv("OTP_MAX_VERIFY_ATTEMPTS", "5")
        )
        self.otp_resend_cooldown_seconds: int = int(
            os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60")
        )
        self.otp_request_rate_limit_per_hour: int = int(
            os.getenv("OTP_REQUEST_RATE_LIMIT_PER_HOUR", "5")
        )
        self.otp_verify_rate_limit_per_hour: int = int(
            os.getenv("OTP_VERIFY_RATE_LIMIT_PER_HOUR", "20")
        )
        # IP-dimension limits (Phase 2 / Identity hardening — security.md
        # §5's second of three documented dimensions, phone/IP/device).
        # Much higher than the phone limits, deliberately: one IP can
        # legitimately serve many users behind NAT/a shared network, and —
        # unlike phone numbers, which every test in this codebase
        # randomizes per call — every TestClient-driven integration test
        # in this suite shares the SAME fixed client IP (starlette's
        # TestClient default) against the SAME real dev Redis instance
        # (there is no dedicated, wiped-per-run test Redis the way there
        # is a dedicated test Postgres database), so this counter
        # persists and accumulates across every test run within the same
        # rolling hour, not just within one pytest invocation — a
        # developer re-running the ~500-test suite even a handful of
        # times while iterating can otherwise exhaust a merely
        # "generous-looking" limit within minutes (this happened during
        # this feature's own development — see ADR discussion). This
        # default is for correctness under iterative local development,
        # not a hardened production value — see this class's own
        # docstring on why that split is expected (security.md §89) and
        # override via the env vars below for production.
        self.otp_request_rate_limit_per_ip_per_hour: int = int(
            os.getenv("OTP_REQUEST_RATE_LIMIT_PER_IP_PER_HOUR", "20000")
        )
        self.otp_verify_rate_limit_per_ip_per_hour: int = int(
            os.getenv("OTP_VERIFY_RATE_LIMIT_PER_IP_PER_HOUR", "40000")
        )
        # HMAC pepper for OTP hashing (domain/otp.py). Deliberately a
        # separate secret from JWT_SECRET so rotating one does not affect
        # the other. Falls back to JWT_SECRET only so local dev works
        # out-of-the-box without a second placeholder in .env.example;
        # production should set OTP_HASH_SECRET explicitly.
        self.otp_hash_secret: str = os.getenv("OTP_HASH_SECRET", self.jwt_secret)

        # --- Refresh tokens / sessions -------------------------------
        self.refresh_token_expire_days: int = int(
            os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30")
        )

        # --- SMS ---------------------------------------------------
        # "dev" (console log) and "msg91" (ADR-0031, 2026-08-25) are the
        # two implemented providers — see sms.py.
        self.sms_provider: str = os.getenv("SMS_PROVIDER", "dev")
        self.msg91_auth_key: str = os.getenv("MSG91_AUTH_KEY", "")
        self.msg91_template_id: str = os.getenv("MSG91_TEMPLATE_ID", "")
        # ADR-0034 (Notification Domain Foundation) — a separate MSG91
        # Flow template for general (non-OTP) notification SMS. Blank by
        # default; sms.py's send_message() raises rather than calling
        # MSG91 with an empty template_id.
        self.msg91_notification_template_id: str = os.getenv(
            "MSG91_NOTIFICATION_TEMPLATE_ID", ""
        )

        self.validate()

    def validate(self) -> None:
        if self.otp_length < 4 or self.otp_length > 10:
            raise ValueError("OTP_LENGTH must be between 4 and 10")
        if self.otp_expiry_seconds <= 0:
            raise ValueError("OTP_EXPIRY_SECONDS must be positive")
        if self.otp_max_verify_attempts <= 0:
            raise ValueError("OTP_MAX_VERIFY_ATTEMPTS must be positive")
        if self.otp_resend_cooldown_seconds < 0:
            raise ValueError("OTP_RESEND_COOLDOWN_SECONDS cannot be negative")
        if self.otp_request_rate_limit_per_hour <= 0:
            raise ValueError("OTP_REQUEST_RATE_LIMIT_PER_HOUR must be positive")
        if self.otp_verify_rate_limit_per_hour <= 0:
            raise ValueError("OTP_VERIFY_RATE_LIMIT_PER_HOUR must be positive")
        if self.otp_request_rate_limit_per_ip_per_hour <= 0:
            raise ValueError("OTP_REQUEST_RATE_LIMIT_PER_IP_PER_HOUR must be positive")
        if self.otp_verify_rate_limit_per_ip_per_hour <= 0:
            raise ValueError("OTP_VERIFY_RATE_LIMIT_PER_IP_PER_HOUR must be positive")
        if self.refresh_token_expire_days <= 0:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be positive")
        if not self.jwt_secret.strip():
            raise ValueError("JWT_SECRET cannot be empty")


identity_settings = IdentitySettings()
