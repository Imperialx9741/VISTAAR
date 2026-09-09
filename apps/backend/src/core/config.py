import os
from decimal import Decimal

from dotenv import load_dotenv

# Loads the repo-root `.env` into the process environment before any
# `os.getenv()` call below runs (2026-09-08 — the SENTRY_DSN wiring is
# what first needed this: every setting here already had a safe
# localhost/disabled default, so local dev never needed `.env` loaded
# at all until a real credential had to reach a plain `uvicorn
# src.main:app --reload` run). No path argument needed:
# `load_dotenv()`'s own `find_dotenv()` walks upward from this file's
# location (apps/backend/src/core/) until it finds a `.env`, which
# resolves to the repo root's regardless of the shell's current working
# directory — verified directly against python-dotenv's own resolution
# behavior, not assumed. `override=False` is python-dotenv's own
# default, kept implicit rather than hardcoded here: a real environment
# variable already set by Docker/Kubernetes always wins over anything
# in `.env`.
load_dotenv()


class Settings:
    """Centralized application and infrastructure settings."""

    def __init__(self) -> None:
        self.APP_ENV: str = os.getenv("APP_ENV", "development")
        self.APP_NAME: str = os.getenv("APP_NAME", "vistaar")
        self.APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")

        self.BACKEND_HOST: str = os.getenv("BACKEND_HOST", "127.0.0.1")
        raw_port = os.getenv("BACKEND_PORT", "8000")
        try:
            self.BACKEND_PORT: int = int(raw_port)
        except ValueError as err:
            raise ValueError(f"BACKEND_PORT must be an integer: {err}") from err

        # CORS (2026-08-29) — the Admin Web frontend (apps/admin-web) runs
        # on its own origin and calls this API directly from the browser
        # (lib/api/client.ts's fetch() calls); without this, every one of
        # those requests is silently rejected by the browser regardless of
        # how correct the backend's own response is (admin-web-
        # implementation-plan.md §6 flagged this gap). Comma-separated so
        # more than one origin (e.g. a later real production admin-web
        # deployment) can be added without a code change. Defaults to
        # Next.js's own default dev port — an engineering placeholder, not
        # an approved production origin (none has been decided yet; see
        # infrastructure/kubernetes/backend-configmap.yaml's own comment).
        raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
        self.CORS_ALLOWED_ORIGINS: list[str] = [
            origin.strip() for origin in raw_origins.split(",") if origin.strip()
        ]

        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql://db_user:db_password@127.0.0.1:5433/vistaar_db",
        )
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        self.KAFKA_BOOTSTRAP_SERVERS: str = os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092"
        )

        # JWT settings were already anticipated in .env.example (Phase 1,
        # Task 7) but not yet wired into application config until this
        # task (Phase 2 / Task 2.1, Identity & Authentication Foundation).
        self.JWT_SECRET: str = os.getenv(
            "JWT_SECRET", "placeholder_jwt_secret_key_minimum_32_characters_long"
        )
        self.JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
            os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
        )

        # Phase 3 / Task 3.2 (Driver Matching). technical-architecture.md
        # §14: "The production search radius and ranking weights remain
        # configurable" — no default is documented anywhere, so this is
        # an engineering choice (implementation-readiness.md §75), not a
        # business decision. 5km is a placeholder starting point, not an
        # approved business value — see ADR-0011.
        self.MATCHING_SEARCH_RADIUS_KM: float = float(
            os.getenv("MATCHING_SEARCH_RADIUS_KM", "5")
        )
        # BR-027: 20 seconds. Configurable only so tests can use a
        # shorter window; not a documented-as-configurable business
        # value — 20 is the approved default and must not be changed in
        # production without a business decision.
        self.MATCHING_OFFER_TTL_SECONDS: int = int(
            os.getenv("MATCHING_OFFER_TTL_SECONDS", "20")
        )

        # Phase 3 / Event & Outbox Foundation (ADR-0017). How often the
        # in-process outbox publisher loop re-polls shared.outbox_events
        # for unpublished rows — an engineering/operational choice
        # (implementation-readiness.md §75's same treatment as the
        # matching settings above), not a business value. 5s balances
        # publish latency against DB polling load for this codebase's
        # current scale.
        self.OUTBOX_PUBLISH_INTERVAL_SECONDS: float = float(
            os.getenv("OUTBOX_PUBLISH_INTERVAL_SECONDS", "5")
        )

        # Phase 18 reliability work (ADR-0071, 2026-09-04): event-contracts.md
        # §30's retry policy is "recommended... exact timings are
        # configurable" — these four settings implement it as a genuine
        # exponential backoff (base * multiplier^(attempt-1), capped at
        # max) rather than reproducing §30's irregular 5s/30s/2m/10m/30m
        # sequence number-for-number. The defaults below are chosen so the
        # sequence this formula actually produces (5s, 25s, ~2m, ~10m,
        # capped at 30m by the 5th attempt) closely tracks that same
        # recommended progression while staying a clean, configurable
        # formula. Governs shared.outbox_events row retry
        # (shared/outbox_publisher.py) — an engineering/operational
        # choice, not a business value, same treatment as
        # OUTBOX_PUBLISH_INTERVAL_SECONDS above.
        self.EVENT_RETRY_MAX_ATTEMPTS: int = int(
            os.getenv("EVENT_RETRY_MAX_ATTEMPTS", "5")
        )
        self.EVENT_RETRY_BACKOFF_BASE_SECONDS: float = float(
            os.getenv("EVENT_RETRY_BACKOFF_BASE_SECONDS", "5")
        )
        self.EVENT_RETRY_BACKOFF_MULTIPLIER: float = float(
            os.getenv("EVENT_RETRY_BACKOFF_MULTIPLIER", "5")
        )
        self.EVENT_RETRY_BACKOFF_MAX_SECONDS: float = float(
            os.getenv("EVENT_RETRY_BACKOFF_MAX_SECONDS", "1800")
        )

        # Phase 16 (Admin, ADR-0023; extended Phase 11/04, ADR-0024, to
        # the driver-facing Wallet Transactions endpoint). api-contracts.md
        # §50: "Maximum page size should be server-configured" — an
        # engineering/operational choice, not a documented business value,
        # same treatment as the matching/outbox settings above. Caps every
        # list endpoint's `page_size` (shared/pagination.py::
        # PageParams.clamp()), admin or not — named generically since it
        # is no longer admin-only.
        self.MAX_PAGE_SIZE: int = int(os.getenv("MAX_PAGE_SIZE", "100"))

        # Phase 06/07 (GPS Verification Foundation, ADR-0028, 2026-08-26).
        # Radius values themselves are the owner-approved business decision
        # this ADR records (50m/100m) — not an engineering placeholder, do
        # not change without a new business decision. The retry count
        # before "manual review" is the same owner decision (3). All three
        # are still exposed via env var only so tests can override them,
        # matching MATCHING_OFFER_TTL_SECONDS's identical treatment above.
        self.RIDE_ARRIVAL_GPS_RADIUS_METERS: float = float(
            os.getenv("RIDE_ARRIVAL_GPS_RADIUS_METERS", "50")
        )
        self.RIDE_COMPLETION_GPS_RADIUS_METERS: float = float(
            os.getenv("RIDE_COMPLETION_GPS_RADIUS_METERS", "100")
        )
        self.RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW: int = int(
            os.getenv("RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW", "3")
        )
        # BR-124 (approved 2026-08-25, ADR-0032): 24 hours — the
        # owner-approved evidence window for a GPS manual review, not an
        # engineering placeholder (same treatment as the two radii
        # above). 86400 = 24 * 3600.
        self.RIDE_GPS_DISPUTE_EVIDENCE_WINDOW_SECONDS: int = int(
            os.getenv("RIDE_GPS_DISPUTE_EVIDENCE_WINDOW_SECONDS", "86400")
        )

        # Ride Modifications (BR-072-081, ADR-0033, 2026-08-25; pickup
        # change simplified by ADR-0056, 2026-08-31). The pickup-change
        # threshold is now 100m (owner decision, ADR-0056 — down from
        # 250m) and purely a free/reject gate: within it, the change
        # applies immediately; beyond it, it is rejected outright, no
        # driver decision and no charge (PricingService.
        # calculate_pickup_change_charge() and the whole driver-decision/
        # customer-confirmation flow were removed by ADR-0056). The
        # destination-extension rate (₹8/km, BR-080) is unaffected by
        # ADR-0056 and unchanged.
        self.RIDE_PICKUP_CHANGE_THRESHOLD_METERS: float = float(
            os.getenv("RIDE_PICKUP_CHANGE_THRESHOLD_METERS", "100")
        )
        self.RIDE_DESTINATION_EXTENSION_RATE_PER_KM: str = os.getenv(
            "RIDE_DESTINATION_EXTENSION_RATE_PER_KM", "8.00"
        )
        # ADR-0033 Decision 9 — engineering judgment, not a business
        # value: no document specifies a tolerance for classifying a new
        # destination as "along the original route" (BR-079/080) vs. "a
        # different route" (BR-081); 200 is the same order of magnitude
        # as the owner-approved 250m pickup threshold above, chosen for
        # consistency, not because it was separately discussed.
        self.RIDE_DESTINATION_ROUTE_DEVIATION_METERS: float = float(
            os.getenv("RIDE_DESTINATION_ROUTE_DEVIATION_METERS", "200")
        )

        # ADR-0039 Decision 3 — engineering judgment, not a business
        # value: neither document specifies how far in advance to warn
        # before a promotion/document expires. 3 days for both, a plain
        # config change either way, no schema/API impact.
        self.PROMOTION_EXPIRY_WARNING_DAYS: int = int(
            os.getenv("PROMOTION_EXPIRY_WARNING_DAYS", "3")
        )
        self.DOCUMENT_EXPIRY_WARNING_DAYS: int = int(
            os.getenv("DOCUMENT_EXPIRY_WARNING_DAYS", "3")
        )

        # Ride-start OTP (api-contracts.md §18, database-design.md §13) —
        # engineering/configuration choices per security.md §89's own
        # "OTP expiry/attempt limits are configuration, not business
        # rules" classification, the same authority
        # modules/identity/config.py's identical settings already rely on.
        # Longer expiry than login's 5 minutes (identity_settings.
        # otp_expiry_seconds) since a driver may take a while to reach the
        # pickup point after ARRIVED before starting the ride.
        self.RIDE_OTP_EXPIRY_SECONDS: int = int(
            os.getenv("RIDE_OTP_EXPIRY_SECONDS", "900")
        )
        self.RIDE_OTP_MAX_ATTEMPTS: int = int(os.getenv("RIDE_OTP_MAX_ATTEMPTS", "5"))
        # Deliberately a separate secret from JWT_SECRET and identity's own
        # OTP_HASH_SECRET, same "rotating one does not affect the others"
        # reasoning identity/config.py already documents for its own pepper.
        self.RIDE_OTP_HASH_SECRET: str = os.getenv(
            "RIDE_OTP_HASH_SECRET", self.JWT_SECRET
        )

        # Object storage (ADR-0031, 2026-08-25). .env.example already
        # provisioned these four (Phase 1) anticipating this; they were
        # never read by any settings class until now. STORAGE_ENDPOINT
        # left unset (empty string) targets real AWS S3 (boto3's default
        # endpoint resolution); setting it points at any S3-compatible
        # alternative (e.g. a local MinIO for dev) without code changes —
        # shared/storage.py treats "" as "use the default AWS endpoint".
        # STORAGE_ACCESS_KEY/SECRET_KEY default to the same non-empty
        # placeholder values .env.example already used (Phase 1) —
        # boto3's request signing needs *some* non-empty credential
        # string to produce a syntactically valid presigned URL even
        # locally/in tests (it does not contact AWS to do so); an empty
        # default would make every local/test presigned-URL call raise
        # botocore.exceptions.NoCredentialsError before ever reaching
        # AWS, unlike a real deployment where these are always set to
        # real values via the environment.
        self.STORAGE_ENDPOINT: str = os.getenv("STORAGE_ENDPOINT", "")
        self.STORAGE_BUCKET: str = os.getenv("STORAGE_BUCKET", "vistaar-storage")
        self.STORAGE_ACCESS_KEY: str = os.getenv(
            "STORAGE_ACCESS_KEY", "fake_access_key"
        )
        self.STORAGE_SECRET_KEY: str = os.getenv(
            "STORAGE_SECRET_KEY", "fake_secret_key"
        )
        self.STORAGE_REGION: str = os.getenv("STORAGE_REGION", "ap-south-1")

        # Push notifications (ADR-0052, 2026-08-28). PUSH_PROVIDER=dev
        # (the default) logs instead of sending — same "always available,
        # no credential needed" treatment identity/config.py's
        # SMS_PROVIDER=dev already established. FCM_SERVICE_ACCOUNT_JSON
        # is a path to a Firebase service-account credentials file (not
        # the credentials themselves inline) — unset by default, since no
        # real Firebase project exists in this environment; required only
        # when PUSH_PROVIDER=fcm is actually selected.
        self.PUSH_PROVIDER: str = os.getenv("PUSH_PROVIDER", "dev")
        self.FCM_SERVICE_ACCOUNT_JSON: str = os.getenv("FCM_SERVICE_ACCOUNT_JSON", "")

        # Sarthi Wallet Recharge (ADR-0060, 2026-09-02). Same dev/real
        # split every other provider integration in this codebase uses —
        # WALLET_RECHARGE_PROVIDER=dev (the default) has no real gateway
        # call to make at all (no order can be created, matching
        # DevConsoleSmsProvider/DevConsolePushProvider's "always
        # available, nothing real happens" treatment). Razorpay is a
        # TEST/DEVELOPMENT gateway only, explicitly not the eventual
        # production choice (SBI, still unselected) — see ADR-0060 for
        # the provider-swap boundary this config is designed around.
        # Deliberately NOT reusing the pre-existing, never-wired
        # PAYMENT_PROVIDER/PAYMENT_API_KEY/PAYMENT_WEBHOOK_SECRET
        # scaffold in .env.example — those were stale placeholders for a
        # customer-facing ride-fare gateway ADR-0025 already ruled out,
        # never read by any code (verified: no match anywhere in this
        # file before this change), and reusing them here would wrongly
        # imply this was always the plan for wallet recharge too.
        self.WALLET_RECHARGE_PROVIDER: str = os.getenv(
            "WALLET_RECHARGE_PROVIDER", "dev"
        )
        self.RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "")
        self.RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "")
        self.RAZORPAY_WEBHOOK_SECRET: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
        # api-contracts.md §35's already-documented "amount >= ₹200"
        # Wallet Recharge validation rule — not a new business value.
        self.WALLET_RECHARGE_MINIMUM_AMOUNT: str = os.getenv(
            "WALLET_RECHARGE_MINIMUM_AMOUNT", "200.00"
        )

        # API Rate Limiting (security.md §20; security-review-2026-09-02.md
        # finding 4.1, HIGH — previously only OTP request/verify had any
        # rate limiting at all, application-level or edge-level). Each
        # limit is per authenticated account (customer/driver/admin id),
        # a fixed one-hour window (shared/rate_limit.py), except the admin
        # blanket limit which uses a one-minute window since admin
        # operators legitimately make many rapid calls in normal use.
        # Exact numbers are engineering configuration, not an approved
        # business rule (security.md §89 explicitly lists "Exact API rate
        # limits" as this kind of open choice) — chosen generously enough
        # not to interfere with genuine use, tight enough to stop a
        # scripted client from hammering an endpoint at unlimited volume;
        # override via these env vars for a real production tuning pass.
        self.RATE_LIMIT_RIDE_CREATE_PER_HOUR: int = int(
            os.getenv("RATE_LIMIT_RIDE_CREATE_PER_HOUR", "20")
        )
        self.RATE_LIMIT_RIDE_CANCEL_PER_HOUR: int = int(
            os.getenv("RATE_LIMIT_RIDE_CANCEL_PER_HOUR", "20")
        )
        self.RATE_LIMIT_RIDE_OFFER_RESPONSE_PER_HOUR: int = int(
            os.getenv("RATE_LIMIT_RIDE_OFFER_RESPONSE_PER_HOUR", "60")
        )
        self.RATE_LIMIT_FARE_CHANGE_PER_HOUR: int = int(
            os.getenv("RATE_LIMIT_FARE_CHANGE_PER_HOUR", "20")
        )
        self.RATE_LIMIT_WALLET_RECHARGE_PER_HOUR: int = int(
            os.getenv("RATE_LIMIT_WALLET_RECHARGE_PER_HOUR", "10")
        )
        self.RATE_LIMIT_PROMOTION_USAGE_PER_HOUR: int = int(
            os.getenv("RATE_LIMIT_PROMOTION_USAGE_PER_HOUR", "20")
        )
        self.RATE_LIMIT_REFERRAL_ATTACH_PER_HOUR: int = int(
            os.getenv("RATE_LIMIT_REFERRAL_ATTACH_PER_HOUR", "10")
        )
        self.RATE_LIMIT_SUPPORT_MESSAGE_PER_HOUR: int = int(
            os.getenv("RATE_LIMIT_SUPPORT_MESSAGE_PER_HOUR", "30")
        )
        self.RATE_LIMIT_EVIDENCE_UPLOAD_PER_HOUR: int = int(
            os.getenv("RATE_LIMIT_EVIDENCE_UPLOAD_PER_HOUR", "30")
        )
        self.RATE_LIMIT_ADMIN_API_PER_MINUTE: int = int(
            os.getenv("RATE_LIMIT_ADMIN_API_PER_MINUTE", "300")
        )

        # Monitoring (ADR-0053, 2026-08-28). Empty SENTRY_DSN (the
        # default) is sentry_sdk's own documented "disabled" state — no
        # custom no-op code needed here, unlike the dev/real provider
        # split every other integration in this codebase needs. Sample
        # rates are deliberately conservative defaults, not 1.0 — full
        # tracing on every request is a cost/volume call for whoever
        # holds the real Sentry account, not this app to make blindly.
        self.SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
        self.SENTRY_TRACES_SAMPLE_RATE: float = float(
            os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")
        )
        self.SENTRY_PROFILES_SAMPLE_RATE: float = float(
            os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.1")
        )
        self.SENTRY_ENVIRONMENT: str = os.getenv("SENTRY_ENVIRONMENT", "development")

        self.validate()

    def validate(self) -> None:
        """Validate configuration values."""
        valid_envs = {"development", "testing", "staging", "production"}
        if self.APP_ENV not in valid_envs:
            raise ValueError(f"APP_ENV must be one of {valid_envs}")

        if not self.APP_NAME.strip():
            raise ValueError("APP_NAME cannot be empty")

        if not self.APP_VERSION.strip():
            raise ValueError("APP_VERSION cannot be empty")

        if not self.BACKEND_HOST.strip():
            raise ValueError("BACKEND_HOST cannot be empty")

        if not (1 <= self.BACKEND_PORT <= 65535):
            raise ValueError("BACKEND_PORT must be between 1 and 65535")

        if not (
            self.DATABASE_URL.startswith("postgresql://")
            or self.DATABASE_URL.startswith("postgres://")
        ):
            raise ValueError(
                "DATABASE_URL must start with postgresql:// or postgres://"
            )

        if not (
            self.REDIS_URL.startswith("redis://")
            or self.REDIS_URL.startswith("rediss://")
        ):
            raise ValueError("REDIS_URL must start with redis:// or rediss://")

        if not self.KAFKA_BOOTSTRAP_SERVERS.strip():
            raise ValueError("KAFKA_BOOTSTRAP_SERVERS cannot be empty")

        if not self.JWT_SECRET.strip():
            raise ValueError("JWT_SECRET cannot be empty")

        # Security review finding, 2026-09-02: the check above only
        # rejected an *empty* JWT_SECRET — a deployment that simply never
        # overrides the env var would boot successfully on the literal
        # placeholder default below, which is committed in this public
        # source file. Since JWT_SECRET signs every access/refresh token
        # this API issues (core/security.py), anyone who has read this
        # repository could forge a valid token for any account, including
        # ADMIN, in that scenario — a full authentication bypass, not a
        # theoretical one. The placeholder stays convenient for local
        # development (APP_ENV=development, the default) but is now
        # rejected outright in every other environment.
        if (
            self.APP_ENV != "development"
            and self.JWT_SECRET
            == "placeholder_jwt_secret_key_minimum_32_characters_long"
        ):
            raise ValueError(
                "JWT_SECRET is still the default placeholder value. Set a "
                "real, randomly-generated secret before running with "
                f"APP_ENV={self.APP_ENV!r}."
            )

        if not self.JWT_ALGORITHM.strip():
            raise ValueError("JWT_ALGORITHM cannot be empty")

        if self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
            raise ValueError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be positive")

        if self.MATCHING_SEARCH_RADIUS_KM <= 0:
            raise ValueError("MATCHING_SEARCH_RADIUS_KM must be positive")

        if self.MATCHING_OFFER_TTL_SECONDS <= 0:
            raise ValueError("MATCHING_OFFER_TTL_SECONDS must be positive")

        if self.OUTBOX_PUBLISH_INTERVAL_SECONDS <= 0:
            raise ValueError("OUTBOX_PUBLISH_INTERVAL_SECONDS must be positive")

        if self.EVENT_RETRY_MAX_ATTEMPTS <= 0:
            raise ValueError("EVENT_RETRY_MAX_ATTEMPTS must be positive")

        if self.EVENT_RETRY_BACKOFF_BASE_SECONDS <= 0:
            raise ValueError("EVENT_RETRY_BACKOFF_BASE_SECONDS must be positive")

        if self.EVENT_RETRY_BACKOFF_MULTIPLIER <= 1:
            raise ValueError(
                "EVENT_RETRY_BACKOFF_MULTIPLIER must be greater than 1 (otherwise "
                "the delay never grows between attempts)"
            )

        if self.EVENT_RETRY_BACKOFF_MAX_SECONDS < self.EVENT_RETRY_BACKOFF_BASE_SECONDS:
            raise ValueError(
                "EVENT_RETRY_BACKOFF_MAX_SECONDS must be >= "
                "EVENT_RETRY_BACKOFF_BASE_SECONDS"
            )

        if self.MAX_PAGE_SIZE <= 0:
            raise ValueError("MAX_PAGE_SIZE must be positive")

        if self.RIDE_ARRIVAL_GPS_RADIUS_METERS <= 0:
            raise ValueError("RIDE_ARRIVAL_GPS_RADIUS_METERS must be positive")

        if self.RIDE_COMPLETION_GPS_RADIUS_METERS <= 0:
            raise ValueError("RIDE_COMPLETION_GPS_RADIUS_METERS must be positive")

        if self.RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW <= 0:
            raise ValueError("RIDE_GPS_MAX_ATTEMPTS_BEFORE_REVIEW must be positive")

        if self.RIDE_GPS_DISPUTE_EVIDENCE_WINDOW_SECONDS <= 0:
            raise ValueError(
                "RIDE_GPS_DISPUTE_EVIDENCE_WINDOW_SECONDS must be positive"
            )

        if self.RIDE_PICKUP_CHANGE_THRESHOLD_METERS <= 0:
            raise ValueError("RIDE_PICKUP_CHANGE_THRESHOLD_METERS must be positive")

        if Decimal(self.RIDE_DESTINATION_EXTENSION_RATE_PER_KM) <= 0:
            raise ValueError("RIDE_DESTINATION_EXTENSION_RATE_PER_KM must be positive")

        if self.RIDE_DESTINATION_ROUTE_DEVIATION_METERS <= 0:
            raise ValueError("RIDE_DESTINATION_ROUTE_DEVIATION_METERS must be positive")

        if Decimal(self.WALLET_RECHARGE_MINIMUM_AMOUNT) <= 0:
            raise ValueError("WALLET_RECHARGE_MINIMUM_AMOUNT must be positive")

        if self.WALLET_RECHARGE_PROVIDER not in {"dev", "razorpay"}:
            raise ValueError(
                "WALLET_RECHARGE_PROVIDER must be one of {'dev', 'razorpay'}"
            )

        for _rate_limit_name in (
            "RATE_LIMIT_RIDE_CREATE_PER_HOUR",
            "RATE_LIMIT_RIDE_CANCEL_PER_HOUR",
            "RATE_LIMIT_RIDE_OFFER_RESPONSE_PER_HOUR",
            "RATE_LIMIT_FARE_CHANGE_PER_HOUR",
            "RATE_LIMIT_WALLET_RECHARGE_PER_HOUR",
            "RATE_LIMIT_PROMOTION_USAGE_PER_HOUR",
            "RATE_LIMIT_REFERRAL_ATTACH_PER_HOUR",
            "RATE_LIMIT_SUPPORT_MESSAGE_PER_HOUR",
            "RATE_LIMIT_EVIDENCE_UPLOAD_PER_HOUR",
            "RATE_LIMIT_ADMIN_API_PER_MINUTE",
        ):
            if getattr(self, _rate_limit_name) <= 0:
                raise ValueError(f"{_rate_limit_name} must be positive")

        if self.PROMOTION_EXPIRY_WARNING_DAYS <= 0:
            raise ValueError("PROMOTION_EXPIRY_WARNING_DAYS must be positive")

        if self.DOCUMENT_EXPIRY_WARNING_DAYS <= 0:
            raise ValueError("DOCUMENT_EXPIRY_WARNING_DAYS must be positive")

        if self.RIDE_OTP_EXPIRY_SECONDS <= 0:
            raise ValueError("RIDE_OTP_EXPIRY_SECONDS must be positive")

        if self.RIDE_OTP_MAX_ATTEMPTS <= 0:
            raise ValueError("RIDE_OTP_MAX_ATTEMPTS must be positive")

        if not self.RIDE_OTP_HASH_SECRET.strip():
            raise ValueError("RIDE_OTP_HASH_SECRET cannot be empty")

        if not self.STORAGE_BUCKET.strip():
            raise ValueError("STORAGE_BUCKET cannot be empty")

        if not self.STORAGE_REGION.strip():
            raise ValueError("STORAGE_REGION cannot be empty")

        if not (0.0 <= self.SENTRY_TRACES_SAMPLE_RATE <= 1.0):
            raise ValueError("SENTRY_TRACES_SAMPLE_RATE must be between 0.0 and 1.0")

        if not (0.0 <= self.SENTRY_PROFILES_SAMPLE_RATE <= 1.0):
            raise ValueError("SENTRY_PROFILES_SAMPLE_RATE must be between 0.0 and 1.0")


settings = Settings()
