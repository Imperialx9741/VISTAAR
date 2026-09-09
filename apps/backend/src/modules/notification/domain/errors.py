"""Domain-level errors for Notification.

`send()`/preferences errors below have no *customer/driver-facing* HTTP
endpoint (ADR-0034 Decision 1), so they never cross an HTTP boundary —
only ever caught (or deliberately left to propagate as a genuine bug)
by whichever service composes NotificationService.send(). ADR-0044's
admin Template Management endpoints are the first exception: the
Template errors at the bottom of this file ARE registered in
shared/api_envelope.py's error-code -> HTTP-status mapping and are
caught by modules/admin/router.py like every other domain's errors.
"""

from __future__ import annotations


class NotificationDomainError(Exception):
    code: str = "NOTIFICATION_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ChannelNotAvailableError(NotificationDomainError):
    """ADR-0034 Decisions 2/3. Raised by NotificationService.send() for
    Channel.PUSH (no device-token data source exists anywhere in this
    codebase) and Channel.WHATSAPP (no BSP chosen, no provider built —
    the owner explicitly asked for a requirements analysis only)."""

    code = "CHANNEL_NOT_AVAILABLE"


class UnknownTemplateError(NotificationDomainError):
    """Raised when template_key has no entry in domain/templates.py's
    lookup — same "client cannot invent a value" treatment this
    codebase gives every other closed vocabulary (e.g. GpsDisputeEvidenceType)."""

    code = "UNKNOWN_TEMPLATE"


# --- Notification Template Management (ADR-0044) ------------------------


class TemplateNotFoundError(NotificationDomainError):
    code = "RESOURCE_NOT_FOUND"


class InvalidTemplateInputError(NotificationDomainError):
    code = "VALIDATION_FAILED"


class InvalidTemplateStateTransitionError(NotificationDomainError):
    """A publish call on a version not in DRAFT status."""

    code = "INVALID_STATE_TRANSITION"


# --- Compose/Send Broadcast + Audience Selection (ADR-0055) --------------


class BroadcastNotFoundError(NotificationDomainError):
    code = "RESOURCE_NOT_FOUND"


class InvalidBroadcastInputError(NotificationDomainError):
    """An unknown channel/audience_type, a blank body, a SELECTED
    audience with no ids, or a non-SELECTED audience carrying ids it
    has no use for."""

    code = "VALIDATION_FAILED"
