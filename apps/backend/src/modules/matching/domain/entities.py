"""Matching domain entity and validation.

Field shapes match docs/04-database/database-design.md §10.1
(matching.ride_offers) exactly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from modules.matching.domain.errors import InvalidCoordinateError

_MIN_LATITUDE = -90.0
_MAX_LATITUDE = 90.0
_MIN_LONGITUDE = -180.0
_MAX_LONGITUDE = 180.0


def validate_driver_coordinates(latitude: float, longitude: float) -> None:
    """api-contracts.md §15's "Valid coordinates" check — presence is
    guaranteed by the request schema (both fields required); only
    standard geographic-range validation happens here. See
    InvalidCoordinateError's docstring for why this isn't shared code
    with modules.ride.domain.entities.validate_coordinates."""
    if not (_MIN_LATITUDE <= latitude <= _MAX_LATITUDE):
        raise InvalidCoordinateError(
            f"latitude must be between {_MIN_LATITUDE} and {_MAX_LATITUDE}."
        )
    if not (_MIN_LONGITUDE <= longitude <= _MAX_LONGITUDE):
        raise InvalidCoordinateError(
            f"longitude must be between {_MIN_LONGITUDE} and {_MAX_LONGITUDE}."
        )


class OfferStatus(StrEnum):
    """Exactly database-design.md §10.1's documented offer statuses.
    This module only ever produces PENDING -> REJECTED and
    PENDING -> EXPIRED (see Offer.new()/MatchingService) — ACCEPTED and
    CANCELLED exist here because they're part of the same documented
    enum a future task (Accept Offer, ADR-0011 Decision 3) will
    transition into, not because this module can reach them yet."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class Offer:
    id: uuid.UUID
    ride_id: uuid.UUID
    driver_id: uuid.UUID
    vehicle_id: uuid.UUID
    status: OfferStatus
    expires_at: datetime
    responded_at: datetime | None
    created_at: datetime

    @staticmethod
    def new(
        *,
        ride_id: uuid.UUID,
        driver_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        ttl_seconds: int,
        now: datetime,
    ) -> Offer:
        """BR-027: the driver has `ttl_seconds` (20, per that rule — see
        core.config.settings.MATCHING_OFFER_TTL_SECONDS's docstring for
        why this is a parameter rather than a hard-coded constant here)
        to respond."""
        return Offer(
            id=uuid.uuid4(),
            ride_id=ride_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            status=OfferStatus.PENDING,
            expires_at=now + timedelta(seconds=ttl_seconds),
            responded_at=None,
            created_at=now,
        )

    def is_expired(self, *, now: datetime) -> bool:
        return self.expires_at <= now
