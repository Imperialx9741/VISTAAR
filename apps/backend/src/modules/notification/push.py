"""Push provider adapters — ADR-0052.

Mirrors modules/identity/sms.py's own dev/real split exactly:
DevConsolePushProvider (always available, no credential, logs instead of
sending) is the default; FcmPushProvider is wired in behind the same
PushProvider protocol (ports.py), selected via PUSH_PROVIDER=fcm.

CAVEAT (same class of flag ADR-0031 gave MSG91's OTP integration): built
from Firebase's publicly documented HTTP v1 API and OAuth2 service-
account JWT-bearer flow, not verified against a live Firebase project —
none exists in this environment. The shape (RS256-signed JWT assertion
exchanged for a bearer token, then a single messages:send call) is
Google's own documented standard for server-to-FCM auth, but should be
confirmed against a real service account before production use.
"""

from __future__ import annotations

import json
import logging
import time

import httpx
import jwt

from core.config import settings

logger = logging.getLogger("vistaar.notification.push")

_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
_FCM_TIMEOUT_SECONDS = 10.0
_TOKEN_TTL_SECONDS = 3600


class DevConsolePushProvider:
    """Local-development push adapter — logs instead of sending a real
    push notification, the same treatment DevConsoleSmsProvider already
    gives SMS. Must not be used in production."""

    async def send(self, token: str, *, title: str, body: str) -> str | None:
        logger.info(
            "DEV PUSH ADAPTER (no real provider configured): "
            "would send push to token=%s title=%r body=%r",
            token,
            title,
            body,
        )
        return None


class FcmDeliveryError(Exception):
    """Raised when FCM's OAuth2 token exchange or messages:send call
    fails (network error or a non-2xx response) — same shape as
    modules.identity.sms.Msg91DeliveryError."""


class FcmPushProvider:
    """Firebase Cloud Messaging HTTP v1 API adapter.

    Reads the service account's `client_email`/`private_key`/
    `token_uri`/`project_id` from the JSON file at
    `service_account_json_path` (Firebase Console's own downloadable
    credentials format) once, at construction. Each send() call performs
    a fresh OAuth2 token exchange rather than caching the access token
    across calls — this class is only ever constructed per-request (see
    get_push_provider()), so there is no long-lived instance to cache
    against; correct over optimal, matching this codebase's own "wired,
    not load-tested" scope for every provider integration built without
    a live account to test against.
    """

    def __init__(
        self,
        *,
        service_account_json_path: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        with open(service_account_json_path, encoding="utf-8") as f:
            account = json.load(f)
        self._client_email: str = account["client_email"]
        self._private_key: str = account["private_key"]
        self._token_uri: str = account.get(
            "token_uri", "https://oauth2.googleapis.com/token"
        )
        self._project_id: str = account["project_id"]
        # transport is None in every real (non-test) construction path,
        # matching Msg91SmsProvider's own identical pattern — tests
        # inject httpx.MockTransport here.
        self._transport = transport

    async def _get_access_token(self) -> str:
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": self._client_email,
                "scope": _FCM_SCOPE,
                "aud": self._token_uri,
                "iat": now,
                "exp": now + _TOKEN_TTL_SECONDS,
            },
            self._private_key,
            algorithm="RS256",
        )
        try:
            async with httpx.AsyncClient(
                timeout=_FCM_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(
                    self._token_uri,
                    data={
                        "grant_type": ("urn:ietf:params:oauth:grant-type:jwt-bearer"),
                        "assertion": assertion,
                    },
                )
        except httpx.HTTPError as exc:
            logger.error("FCM OAuth2 token exchange failed (network error): %s", exc)
            raise FcmDeliveryError(str(exc)) from exc

        if response.status_code >= 400:
            logger.error(
                "FCM OAuth2 token exchange failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise FcmDeliveryError(
                f"FCM token exchange returned HTTP {response.status_code}: "
                f"{response.text}"
            )
        access_token = response.json().get("access_token")
        if not access_token:
            raise FcmDeliveryError("FCM token exchange returned no access_token.")
        return str(access_token)

    async def send(self, token: str, *, title: str, body: str) -> str | None:
        access_token = await self._get_access_token()
        url = _FCM_SEND_URL.format(project_id=self._project_id)
        try:
            async with httpx.AsyncClient(
                timeout=_FCM_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={
                        "message": {
                            "token": token,
                            "notification": {"title": title, "body": body},
                        }
                    },
                )
        except httpx.HTTPError as exc:
            logger.error("FCM send failed (network error): %s", exc)
            raise FcmDeliveryError(str(exc)) from exc

        if response.status_code >= 400:
            logger.error(
                "FCM send failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise FcmDeliveryError(
                f"FCM returned HTTP {response.status_code}: {response.text}"
            )

        name = response.json().get("name")
        return str(name) if name is not None else None


def get_push_provider() -> DevConsolePushProvider | FcmPushProvider:
    """Factory for the configured push provider — mirrors
    modules.identity.sms.get_sms_provider()'s own shape exactly."""
    provider = settings.PUSH_PROVIDER
    if provider == "dev":
        return DevConsolePushProvider()
    if provider == "fcm":
        if not settings.FCM_SERVICE_ACCOUNT_JSON:
            raise ValueError(
                "PUSH_PROVIDER=fcm requires FCM_SERVICE_ACCOUNT_JSON to be set "
                "to a real service-account credentials file path."
            )
        return FcmPushProvider(
            service_account_json_path=settings.FCM_SERVICE_ACCOUNT_JSON
        )
    raise NotImplementedError(
        f"PUSH_PROVIDER={provider!r} is not implemented. Only 'dev' and "
        "'fcm' exist — ADR-0052 scoped this to Firebase (already owner-"
        "approved, ADR-0034 Decision 2)."
    )
