"""SMS provider adapters.

Originally only a development (console-log) adapter existed —
``get_sms_provider()`` was deliberately built as "the single place a real
provider will be wired in later, behind the same ``SmsProvider`` protocol
(ports.py) — no call site elsewhere in this module will need to change."
ADR-0031 (2026-08-25) does exactly that: the project owner selected
MSG91, and ``Msg91SmsProvider`` below is wired in behind the same
protocol, selected via ``SMS_PROVIDER=msg91``. ``SMS_PROVIDER=dev``
(console log) remains the default — no existing behavior changes unless
the env var is explicitly set.
"""

from __future__ import annotations

import logging

import httpx

from modules.identity.config import identity_settings

logger = logging.getLogger("vistaar.identity.sms")

_MSG91_OTP_URL = "https://control.msg91.com/api/v5/otp"
# MSG91's v5 Flow API — general (non-OTP) transactional SMS, distinct
# from the OTP-specific endpoint above. Added for ADR-0034
# (Notification Domain Foundation): modules.notification.service.
# NotificationService reuses this same SMS integration, generalized
# beyond OTP-only sending — see send_message() below and that ADR's own
# caveat (this shape is unverified against a live MSG91 account, the
# same class of flag the OTP integration already carries).
_MSG91_FLOW_URL = "https://control.msg91.com/api/v5/flow/"
_MSG91_TIMEOUT_SECONDS = 10.0


class DevConsoleSmsProvider:
    """Local-development SMS adapter.

    Logs the OTP to the server-side application log instead of sending a
    real SMS. This is intentionally NEVER returned to the HTTP client —
    security.md §5 requires "OTP must never be returned by the API"; this
    adapter only writes to the backend's own log stream, the same place
    a real provider's delivery confirmation would be logged.

    Must not be used in production.
    """

    async def send_otp(self, phone_number: str, otp: str) -> None:
        logger.info(
            "DEV SMS ADAPTER (no real provider configured): "
            "would send OTP to %s. OTP=%s (development only — never do "
            "this in a real log in production)",
            phone_number,
            otp,
        )

    async def send_message(self, phone_number: str, message: str) -> str | None:
        """ADR-0034 — the generic (non-OTP) counterpart to send_otp()
        above, used by modules.notification.service.NotificationService.
        Same "log instead of sending" development treatment."""
        logger.info(
            "DEV SMS ADAPTER (no real provider configured): "
            "would send message to %s: %s",
            phone_number,
            message,
        )
        return None


class Msg91DeliveryError(Exception):
    """Raised when MSG91's OTP-send API call fails (network error or a
    non-2xx / error-flagged response). Deliberately not surfaced to the
    HTTP client as a specific error code — the caller (identity's
    request_otp() composition) already treats OTP delivery as best-effort
    from the client's perspective (the OTP challenge itself is created
    either way; see modules/identity/service.py)."""


class Msg91SmsProvider:
    """MSG91 v5 OTP API adapter.

    CAVEAT (see ADR-0031 Decision 1): built from general knowledge of
    MSG91's public v5 OTP API, not verified against a live MSG91 account
    in this environment (none is configured here). The overall shape —
    `authkey` header, template-based send, a custom `otp` value rather
    than letting MSG91 generate one (this codebase already owns OTP
    generation/hashing end-to-end, modules.identity.domain.otp) — is
    standard for this class of provider, but exact field names/response
    shape should be confirmed against MSG91's current API reference and
    a real account before production use.
    """

    def __init__(
        self,
        *,
        auth_key: str,
        template_id: str,
        notification_template_id: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._auth_key = auth_key
        self._template_id = template_id
        # ADR-0034 — a separate MSG91 Flow template, distinct from the
        # OTP template_id above; send_message() below needs one
        # pre-configured on MSG91's dashboard to accept a single
        # free-text variable. Empty by default (no live account exists
        # in this environment to configure one against) — send_message()
        # raises rather than calling MSG91 with an empty template_id.
        self._notification_template_id = notification_template_id
        # transport is None in every real (non-test) construction path —
        # get_sms_provider() below never passes one, so httpx uses its
        # own real network transport. Tests inject httpx.MockTransport
        # here to exercise this adapter without a real MSG91 account or
        # network access.
        self._transport = transport

    async def send_otp(self, phone_number: str, otp: str) -> None:
        # MSG91 expects a bare national number (no leading "+") for the
        # `mobile` param in its documented examples; this codebase's own
        # phone numbers are always E.164 (+91XXXXXXXXXX — modules.identity
        # .domain.phone_number), so the leading "+" is stripped here, at
        # the adapter boundary, rather than changing how phone numbers
        # are stored/validated everywhere else.
        mobile = phone_number.removeprefix("+")
        try:
            async with httpx.AsyncClient(
                timeout=_MSG91_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(
                    _MSG91_OTP_URL,
                    headers={"authkey": self._auth_key},
                    params={
                        "template_id": self._template_id,
                        "mobile": mobile,
                        "otp": otp,
                    },
                )
        except httpx.HTTPError as exc:
            logger.error("MSG91 OTP send failed (network error): %s", exc)
            raise Msg91DeliveryError(str(exc)) from exc

        if response.status_code >= 400:
            logger.error(
                "MSG91 OTP send failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise Msg91DeliveryError(
                f"MSG91 returned HTTP {response.status_code}: {response.text}"
            )

        body = response.json()
        # MSG91's documented success envelope is {"type": "success", ...};
        # anything else (e.g. {"type": "error", "message": "..."}) is
        # treated as a delivery failure even on HTTP 200 — MSG91's API is
        # known to return 200 with an in-body error for some failure
        # classes (invalid template_id, insufficient balance, etc.).
        if body.get("type") != "success":
            logger.error("MSG91 OTP send returned a non-success body: %s", body)
            raise Msg91DeliveryError(f"MSG91 returned a non-success body: {body!r}")

    async def send_message(self, phone_number: str, message: str) -> str | None:
        """ADR-0034 — general (non-OTP) SMS via MSG91's v5 Flow API,
        used by modules.notification.service.NotificationService. Same
        "unverified against a live account" caveat as this class's own
        docstring, plus: real delivery in production additionally needs
        `message` to match a DLT-registered template (an Indian-telecom
        regulatory requirement for commercial SMS, not an MSG91-specific
        detail) — this call sends `message` as a single template
        variable (VAR1) to a pre-configured "generic notification" Flow,
        which is itself a real-account configuration step nothing in
        this environment can perform. Returns MSG91's request_id as the
        provider_reference on success, matching NotificationService's
        own `provider_reference` field."""
        if not self._notification_template_id:
            raise Msg91DeliveryError(
                "MSG91_NOTIFICATION_TEMPLATE_ID is not configured — cannot "
                "send a general notification SMS."
            )
        mobile = phone_number.removeprefix("+")
        try:
            async with httpx.AsyncClient(
                timeout=_MSG91_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(
                    _MSG91_FLOW_URL,
                    headers={
                        "authkey": self._auth_key,
                        "content-type": "application/json",
                    },
                    json={
                        "template_id": self._notification_template_id,
                        "recipients": [{"mobiles": mobile, "VAR1": message}],
                    },
                )
        except httpx.HTTPError as exc:
            logger.error("MSG91 notification SMS send failed (network error): %s", exc)
            raise Msg91DeliveryError(str(exc)) from exc

        if response.status_code >= 400:
            logger.error(
                "MSG91 notification SMS send failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            raise Msg91DeliveryError(
                f"MSG91 returned HTTP {response.status_code}: {response.text}"
            )

        body = response.json()
        if body.get("type") != "success":
            logger.error(
                "MSG91 notification SMS send returned a non-success body: %s", body
            )
            raise Msg91DeliveryError(f"MSG91 returned a non-success body: {body!r}")
        request_id = body.get("request_id")
        return str(request_id) if request_id is not None else None


def get_sms_provider() -> DevConsoleSmsProvider | Msg91SmsProvider:
    """Factory for the configured SMS provider.

    ``identity_settings.sms_provider`` is read so that selecting a real
    provider later is a config change plus adding one branch here — not a
    change to any of the code that calls this factory.
    """
    provider = identity_settings.sms_provider
    if provider == "dev":
        return DevConsoleSmsProvider()
    if provider == "msg91":
        if not identity_settings.msg91_auth_key or not (
            identity_settings.msg91_template_id
        ):
            raise ValueError(
                "SMS_PROVIDER=msg91 requires MSG91_AUTH_KEY and "
                "MSG91_TEMPLATE_ID to both be set."
            )
        return Msg91SmsProvider(
            auth_key=identity_settings.msg91_auth_key,
            template_id=identity_settings.msg91_template_id,
            # ADR-0034 — deliberately NOT validated as required here,
            # unlike msg91_template_id above: OTP sending (this factory's
            # original, still-primary purpose) must keep working even
            # when no notification template is configured yet.
            # send_message() itself raises if this is blank and actually
            # called.
            notification_template_id=identity_settings.msg91_notification_template_id,
        )
    raise NotImplementedError(
        f"SMS_PROVIDER={provider!r} is not implemented. Only 'dev' and "
        "'msg91' exist — integrating another provider (Twilio/Exotel/"
        "AWS SNS/WhatsApp/etc.) is out of scope of ADR-0031."
    )
