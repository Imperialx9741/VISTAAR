"""Unit tests for the pure Matching domain layer (no DB, no HTTP, no
Redis)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from modules.matching.domain.entities import (
    Offer,
    OfferStatus,
    validate_driver_coordinates,
)
from modules.matching.domain.errors import InvalidCoordinateError

RIDE_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()
VEHICLE_ID = uuid.uuid4()
NOW = datetime.now(UTC)


def _new_offer(ttl_seconds: int = 20) -> Offer:
    return Offer.new(
        ride_id=RIDE_ID,
        driver_id=DRIVER_ID,
        vehicle_id=VEHICLE_ID,
        ttl_seconds=ttl_seconds,
        now=NOW,
    )


def test_new_offer_starts_pending() -> None:
    offer = _new_offer()
    assert offer.status is OfferStatus.PENDING
    assert offer.responded_at is None


def test_new_offer_expires_ttl_seconds_after_now() -> None:
    """BR-027: 20 seconds."""
    offer = _new_offer(ttl_seconds=20)
    assert offer.expires_at == NOW + timedelta(seconds=20)


def test_offer_is_expired_after_its_expiry_time() -> None:
    offer = _new_offer(ttl_seconds=20)
    assert offer.is_expired(now=NOW + timedelta(seconds=21)) is True


def test_offer_is_not_expired_before_its_expiry_time() -> None:
    offer = _new_offer(ttl_seconds=20)
    assert offer.is_expired(now=NOW + timedelta(seconds=10)) is False


def test_offer_is_expired_exactly_at_expiry_time() -> None:
    offer = _new_offer(ttl_seconds=20)
    assert offer.is_expired(now=NOW + timedelta(seconds=20)) is True


@pytest.mark.parametrize("bad_latitude", [-90.1, 90.1])
def test_invalid_driver_latitude_is_rejected(bad_latitude: float) -> None:
    with pytest.raises(InvalidCoordinateError):
        validate_driver_coordinates(bad_latitude, 85.1376)


@pytest.mark.parametrize("bad_longitude", [-180.1, 180.1])
def test_invalid_driver_longitude_is_rejected(bad_longitude: float) -> None:
    with pytest.raises(InvalidCoordinateError):
        validate_driver_coordinates(25.5941, bad_longitude)


def test_valid_driver_coordinates_do_not_raise() -> None:
    validate_driver_coordinates(25.5941, 85.1376)
