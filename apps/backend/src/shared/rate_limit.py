"""Generic Redis-backed API rate limiting (security.md §20).

security-review-2026-09-02.md finding 4.1 (HIGH, open): only OTP
request/verify (modules/identity/rate_limit.py's own
RedisOtpRateLimiter) had any rate limiting at all — none of the other
~13 categories security.md §20 lists did, at the application layer or
the infrastructure edge. That review recommended application-level
rate limiting, reusing the existing Redis infrastructure, for the
endpoints where the true business identity (customer_id/driver_id/
admin id) matters — this module is that recommendation, implemented.

This generalizes RedisOtpRateLimiter's own algorithm (a fixed-window
counter: INCR + EXPIRE) rather than replacing it — OTP request/verify
keep their dedicated, already-tested implementation unchanged, since it
also has its own IP dimension and resend-cooldown concept this generic
module deliberately does not need (every endpoint this module protects
requires a real access token first, so the authenticated account id is
always available and is a materially better rate-limiting dimension
than IP — unlike OTP request/verify, which run *before* any session
exists).

Exact numeric limits are engineering configuration, not an approved
business rule — security.md §89 explicitly lists "Exact API rate
limits" as exactly that kind of open configuration choice, the same
treatment modules/identity/config.py's own OTP rate-limit defaults
already get. See core/config.py's RATE_LIMIT_* settings for the actual
per-category values.

Deliberately takes no dependency on core.config or shared.api_envelope
— shared/ modules take configuration as parameters and let each caller
build its own response, the same split shared/pagination.py's own
docstring documents for exactly this reason.
"""

from __future__ import annotations

from redis.asyncio import Redis


class RateLimitedError(Exception):
    """Maps to RATE_LIMITED (api-contracts.md §49, HTTP 429) — the same
    error code modules/identity/domain/errors.py's OtpRateLimitedError
    already uses. Reused deliberately (one error code for "you are
    rate-limited," regardless of which limiter caught it) rather than
    minted fresh per category."""

    code = "RATE_LIMITED"

    def __init__(
        self, message: str = "Too many requests. Please try again later."
    ) -> None:
        super().__init__(message)
        self.message = message


class RateLimiter:
    """A fixed-window counter, generic over key/limit/window — exactly
    RedisOtpRateLimiter's own INCR+EXPIRE algorithm, parameterized
    instead of hardcoded per call site, so one implementation serves
    every category in security.md §20 this pass adds."""

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def check_and_increment(
        self, *, key: str, limit: int, window_seconds: int
    ) -> None:
        """Raises RateLimitedError once `key`'s count exceeds `limit`
        within the current `window_seconds` window. The window starts
        the moment the first request in it is counted (`count == 1`)
        and is not reset early by a request that itself gets rejected —
        matching RedisOtpRateLimiter's own behavior, and correct: a
        client hammering an endpoint past its limit should not be able
        to extend or reset its own window by continuing to retry."""
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, window_seconds)
        if count > limit:
            raise RateLimitedError()


def rate_limit_key(*, category: str, identity: str) -> str:
    """`category` is a short, stable name for the endpoint/action being
    limited (e.g. "ride_create", "wallet_recharge") — distinct
    categories never share a counter even for the same identity, so a
    driver hitting their wallet-recharge limit does not also count
    against their ride-offer-response limit. `identity` is normally the
    authenticated account's id (str(account.id)); the one exception is
    the admin-API blanket limiter (modules/admin/dependencies.py), which
    also uses the authenticated admin's account id, not an IP — every
    endpoint this module protects requires a real access token first."""
    return f"ratelimit:{category}:{identity}"
