import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

import sentry_sdk
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis
from sentry_sdk.types import Event, Hint
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from core.kafka import check_kafka_connection
from core.redis import get_redis
from modules.admin.router import router as admin_router
from modules.customer.router import router as customer_router
from modules.driver.router import router as driver_router
from modules.identity.router import router as identity_router
from modules.matching.router import location_router, offers_router
from modules.notification.consumer import NotificationConsumer
from modules.notification.router import router as notification_router
from modules.promotion.router import router as promotion_router
from modules.referral.router import router as referral_router
from modules.ride.router import router as ride_router
from modules.safety.router import router as safety_router
from modules.support.router import router as support_router
from modules.vehicle.router import router as vehicle_router
from modules.wallet.router import router as wallet_router
from modules.wallet.router import webhook_router as wallet_webhook_router
from shared.api_envelope import error_envelope, new_request_id
from shared.outbox_publisher import OutboxPublisher, run_outbox_publisher_loop
from shared.security_headers import SecurityHeadersMiddleware

# Real bug found 2026-09-08 while debugging "OTP never arrives" on a
# fresh local run: this app has always had every module call
# `logging.getLogger("vistaar...")` (or `__name__`) and log real,
# useful INFO-level messages (most critically,
# modules/identity/sms.py's own DevConsoleSmsProvider, which exists
# specifically so a developer can read the OTP off this same console
# when SMS_PROVIDER=dev — its own docstring already documents that as
# the intended flow) — but nothing anywhere in this codebase ever
# called `logging.basicConfig()` (or an equivalent dictConfig). Python
# loggers with no handler attached and no explicit level fall back to
# the root logger's own default (WARNING, with no handler at all until
# something configures one), so every INFO/DEBUG log in this entire
# backend was silently swallowed — not just this one message. Verified
# directly, not assumed: ran a real local server and confirmed
# uvicorn's own startup/access lines appeared while
# `DevConsoleSmsProvider`'s OTP line never did, for a real
# `POST /auth/otp/request` call. INFO is a safe default for every
# environment, not a dev-only convenience — nothing in this codebase's
# security posture relies on INFO logs being invisible (the opposite:
# security.md §65/main.py's own `_scrub_sensitive_sentry_data` above
# assume real log statements exist and get scrubbed, not that logging
# itself is off), and `DevConsoleSmsProvider` is already gated to
# SMS_PROVIDER=dev by construction, never reachable in a real
# deployment regardless of this change.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

logger = logging.getLogger(__name__)

# Monitoring (ADR-0053, 2026-08-28). Called at module import time, before
# the FastAPI app itself is constructed, so a startup-time error is
# captured too. An empty SENTRY_DSN (the default — no real Sentry
# account exists in this environment) is sentry_sdk's own documented
# "disabled" state, not a special case this codebase had to build.


def _scrub_sensitive_sentry_data(event: Event, hint: Hint) -> Event | None:
    """Security review finding, 2026-09-02 (security.md §65's "never log
    OTP/access tokens/refresh tokens" applies just as much to error-
    tracking events as to the application's own logger). sentry-sdk's
    built-in `EventScrubber` already redacts common sensitive keys by
    default, and `send_default_pii=False` below already keeps full
    request bodies/headers out unless explicitly enabled — this is
    deliberate defense-in-depth on top of both, for the one case those
    don't fully cover: an `Authorization`/`Cookie` header captured
    verbatim on `event["request"]["headers"]` if a future change ever
    flips `send_default_pii` without re-checking this file. Never blocks
    sending the event — only strips these two header values in place.
    """
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            for header_name in list(headers):
                if header_name.lower() in {"authorization", "cookie"}:
                    headers[header_name] = "[Filtered]"
    return event


sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    environment=settings.SENTRY_ENVIRONMENT,
    traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
    profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
    # Explicit, not relied on as an unstated SDK default — security.md
    # §57/§65: request bodies/headers/IP addresses may contain OTPs,
    # tokens, or other sensitive data and must not be sent to a
    # third-party error tracker by default.
    send_default_pii=False,
    before_send=_scrub_sensitive_sentry_data,
)


async def _start_and_run_outbox_publisher(publisher: OutboxPublisher) -> None:
    """Retries starting the Kafka producer until it succeeds — a Kafka
    outage at process-boot time must never prevent the API itself from
    serving HTTP traffic (same "infrastructure unavailable degrades,
    doesn't crash" tolerance every health check in this file already
    has). Runs as its own background task (see lifespan() below) so
    app startup itself is never blocked waiting for Kafka."""
    while True:
        try:
            await publisher.start()
            break
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Could not start the outbox publisher's Kafka producer; "
                "retrying in %ss.",
                settings.OUTBOX_PUBLISH_INTERVAL_SECONDS,
            )
            await asyncio.sleep(settings.OUTBOX_PUBLISH_INTERVAL_SECONDS)

    await run_outbox_publisher_loop(
        publisher, interval_seconds=settings.OUTBOX_PUBLISH_INTERVAL_SECONDS
    )


async def _start_and_run_notification_consumer(consumer: NotificationConsumer) -> None:
    """Same "retry Kafka connection forever, never block API startup"
    tolerance as _start_and_run_outbox_publisher() above — ADR-0038."""
    while True:
        try:
            await consumer.start()
            break
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Could not start the notification consumer's Kafka "
                "connection; retrying in %ss.",
                settings.OUTBOX_PUBLISH_INTERVAL_SECONDS,
            )
            await asyncio.sleep(settings.OUTBOX_PUBLISH_INTERVAL_SECONDS)

    await consumer.consume_forever()


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """ADR-0017: starts the in-process outbox publisher loop alongside
    the API server — not a separate worker process (the Background
    Worker Foundation technology decision, Phase 01/18, remains
    unapproved and unneeded for this). ADR-0038 adds the Notification
    Kafka consumer the same way, for the same reason."""
    publisher = OutboxPublisher()
    publisher_task = asyncio.create_task(_start_and_run_outbox_publisher(publisher))

    consumer = NotificationConsumer()
    consumer_task = asyncio.create_task(_start_and_run_notification_consumer(consumer))
    try:
        yield
    finally:
        publisher_task.cancel()
        consumer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await publisher_task
        with contextlib.suppress(asyncio.CancelledError):
            await consumer_task
        await publisher.stop()
        await consumer.stop()


app = FastAPI(
    title="VISTAAR Backend",
    description="VISTAAR Ride Matching Platform Backend",
    version="0.1.0",
    lifespan=lifespan,
)

# Auth-layer dependency failures (modules/identity/dependencies.py's
# get_current_account/require_account_type, modules/admin/dependencies.py's
# rate-limit check) raise a plain FastAPI HTTPException(detail="SOME_CODE")
# rather than returning this codebase's own error_envelope() shape every
# route handler's own try/except uses — Depends() functions can only raise,
# not return a JSONResponse in place of continuing, so there was previously
# no way for them to produce the enveloped shape. Found 2026-09-08 while
# diagnosing an admin-web bug report: a stale/invalid token produced a raw
# {"detail": "AUTH_INVALID"} response, which admin-web's client (lib/api/
# client.ts, expecting {data, error: {code, message}, request_id} on every
# endpoint per api-contracts.md §3) couldn't parse into a real message —
# it fell back to a bare "UNKNOWN_ERROR"/the HTTP reason phrase, exactly
# the confusing, unhelpful error text that report showed.
#
# Only reshapes the body for `detail` values matching one of the six known
# short auth-layer codes below — status_code is always preserved exactly
# as raised. Anything else (e.g. /health/db's free-form "Database
# connectivity check failed: ..." messages) falls through to FastAPI's own
# default handler, completely unchanged — this deliberately does not
# reshape every HTTPException in the app, only ones this codebase's own
# error-code vocabulary (api-contracts.md §49) already recognizes.
_HTTP_EXCEPTION_ENVELOPE_MESSAGES: dict[str, str] = {
    "AUTH_REQUIRED": "Authentication is required for this endpoint.",
    "AUTH_INVALID": "The access token is invalid, expired, or was not issued for this purpose.",
    "ACCOUNT_SUSPENDED": "This account is suspended.",
    "FORBIDDEN": "You do not have permission to perform this action.",
    "RATE_LIMITED": "Too many requests. Please wait and try again.",
}


@app.exception_handler(HTTPException)
async def _enveloped_http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    message = (
        _HTTP_EXCEPTION_ENVELOPE_MESSAGES.get(exc.detail)
        if isinstance(exc.detail, str)
        else None
    )
    if message is None:
        return await http_exception_handler(request, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(exc.detail, message, request_id=new_request_id()),
        headers=exc.headers,
    )


# ADR-0036: security.md §64's response headers, on every request.
app.add_middleware(SecurityHeadersMiddleware)

# CORS (2026-08-29, admin-web-implementation-plan.md §6) — added after
# SecurityHeadersMiddleware so it becomes the outermost middleware
# (Starlette's add_middleware() prepends, so the last one added wraps
# every other one) — CORSMiddleware must wrap everything, including
# error responses and other middleware, to short-circuit preflight
# OPTIONS requests and attach Access-Control-* headers universally.
# `allow_credentials=False` (the safe default): the Admin Web's own
# fetch() calls (lib/api/client.ts) send a bearer token via the
# Authorization header, not cookies — that's not a CORS "credential"
# and needs no special browser opt-in, so there is no reason to enable
# the credentialed mode (which would also forbid a wildcard origin
# list if one were ever used).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(identity_router)
app.include_router(customer_router)
app.include_router(driver_router)
app.include_router(vehicle_router)
app.include_router(admin_router)
app.include_router(ride_router)
app.include_router(location_router)
app.include_router(offers_router)
app.include_router(wallet_router)
app.include_router(wallet_webhook_router)
app.include_router(promotion_router)
app.include_router(referral_router)
app.include_router(safety_router)
app.include_router(support_router)
app.include_router(notification_router)

# Monitoring (ADR-0053, 2026-08-28). Exposes GET /metrics — standard
# HTTP request metrics (latency, count, status code, path), no
# credential needed at all (Prometheus scrapes a plain HTTP endpoint).
# `should_group_untemplated=True` (instrumentator's own default) groups
# 404s on unmatched paths under one label rather than one per garbage
# URL, avoiding unbounded cardinality from scanning/probing traffic.
Instrumentator().instrument(app).expose(app)


@app.get("/")
async def read_root() -> dict[str, str]:
    return {"message": "Welcome to VISTAAR Backend API"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "OK"}


@app.get("/health/db")
def db_health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Database connectivity check failed: {str(e)}"
        ) from e


@app.get("/health/redis")
async def redis_health_check(
    redis_client: Redis = Depends(get_redis),
) -> dict[str, str]:
    try:
        pong = await redis_client.ping()
        if pong:
            return {"status": "healthy", "redis": "connected"}
        raise HTTPException(status_code=503, detail="Redis PING failed")
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Redis connectivity check failed: {str(e)}"
        ) from e


@app.get("/health/kafka")
async def kafka_health_check() -> dict[str, str]:
    try:
        await check_kafka_connection()
        return {"status": "healthy", "kafka": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Kafka connectivity check failed: {str(e)}"
        ) from e
