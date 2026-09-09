"""Redis-backed OTP request/verify rate limiting.

Uses Redis for exactly what the task's REDIS section scopes: "rate-limiting
state" and "short-lived authentication state" — never as the source of
truth for identity (that remains PostgreSQL, per core/database.py and
modules/identity/repositories.py).

Phone-number and IP-address dimensions are both implemented (see ports.py's
OtpRateLimiter docstring for why the device/session dimension is still
deferred — it needs a new API contract, not just more rate-limiting logic).
Uses a fixed-window counter (INCR + EXPIRE) — simple, and sufficient for a
foundational rate limiter; a sliding-window algorithm can replace this
later behind the same OtpRateLimiter protocol without touching callers.
"""

from __future__ import annotations

from redis.asyncio import Redis

from modules.identity.config import identity_settings
from modules.identity.domain.errors import OtpRateLimitedError, OtpResendCooldownError

_REQUEST_KEY = "identity:otp:request:{phone}"
_COOLDOWN_KEY = "identity:otp:cooldown:{phone}"
_VERIFY_KEY = "identity:otp:verify:{phone}"
_REQUEST_IP_KEY = "identity:otp:request:ip:{ip}"
_VERIFY_IP_KEY = "identity:otp:verify:ip:{ip}"

_ONE_HOUR_SECONDS = 3600


class RedisOtpRateLimiter:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def check_and_increment_request(self, phone: str) -> None:
        cooldown_key = _COOLDOWN_KEY.format(phone=phone)
        if await self._redis.exists(cooldown_key):
            raise OtpResendCooldownError(
                "Please wait before requesting another OTP for this number."
            )

        request_key = _REQUEST_KEY.format(phone=phone)
        count = await self._redis.incr(request_key)
        if count == 1:
            await self._redis.expire(request_key, _ONE_HOUR_SECONDS)
        if count > identity_settings.otp_request_rate_limit_per_hour:
            raise OtpRateLimitedError(
                "Too many OTP requests for this number. Try again later."
            )

        if identity_settings.otp_resend_cooldown_seconds > 0:
            # Redis's SET ... EX requires a positive expiry — 0 is a
            # legitimate "cooldown disabled" configuration (config.py's
            # own validate() allows it), not an error, so skip setting
            # the key entirely rather than let that call fail.
            await self._redis.set(
                cooldown_key, "1", ex=identity_settings.otp_resend_cooldown_seconds
            )

    async def check_and_increment_verify_attempt(self, phone: str) -> None:
        verify_key = _VERIFY_KEY.format(phone=phone)
        count = await self._redis.incr(verify_key)
        if count == 1:
            await self._redis.expire(verify_key, _ONE_HOUR_SECONDS)
        if count > identity_settings.otp_verify_rate_limit_per_hour:
            raise OtpRateLimitedError(
                "Too many verification attempts for this number. Try again later."
            )

    async def check_and_increment_request_ip(self, ip_address: str) -> None:
        request_ip_key = _REQUEST_IP_KEY.format(ip=ip_address)
        count = await self._redis.incr(request_ip_key)
        if count == 1:
            await self._redis.expire(request_ip_key, _ONE_HOUR_SECONDS)
        if count > identity_settings.otp_request_rate_limit_per_ip_per_hour:
            raise OtpRateLimitedError(
                "Too many OTP requests from this network. Try again later."
            )

    async def check_and_increment_verify_attempt_ip(self, ip_address: str) -> None:
        verify_ip_key = _VERIFY_IP_KEY.format(ip=ip_address)
        count = await self._redis.incr(verify_ip_key)
        if count == 1:
            await self._redis.expire(verify_ip_key, _ONE_HOUR_SECONDS)
        if count > identity_settings.otp_verify_rate_limit_per_ip_per_hour:
            raise OtpRateLimitedError(
                "Too many verification attempts from this network. Try again later."
            )
