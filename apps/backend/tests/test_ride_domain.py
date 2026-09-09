"""Unit tests for the pure Ride domain layer (no DB, no HTTP)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from modules.ride.domain.entities import (
    SCHEDULED_RIDE_LOCK_IN_WINDOW,
    Ride,
    RideStatus,
    validate_coordinates,
    validate_linked_contact,
    validate_scheduled_for,
)
from modules.ride.domain.errors import (
    InvalidCoordinateError,
    InvalidLinkedContactError,
    InvalidScheduledForError,
)
from modules.vehicle.domain.entities import VehicleCategory
from modules.vehicle.domain.errors import InvalidCabTierError, InvalidCategoryError

CUSTOMER_ID = uuid.uuid4()
NOW = datetime.now(UTC)


def _new_ride(**overrides: object) -> Ride:
    defaults: dict[str, object] = {
        "pickup_latitude": 25.5941,
        "pickup_longitude": 85.1376,
        "destination_latitude": 25.6120,
        "destination_longitude": 85.1580,
        "vehicle_category": "CAB",
        "cab_tier": "ECO",
    }
    defaults.update(overrides)
    # ADR-0020 Decision 1: cab_tier is only valid alongside CAB — a test
    # overriding vehicle_category to something else must not also send
    # the CAB-only default through.
    if defaults["vehicle_category"] != "CAB" and "cab_tier" not in overrides:
        defaults.pop("cab_tier")
    return Ride.new(customer_id=CUSTOMER_ID, now=NOW, **defaults)  # type: ignore[arg-type]


def test_new_ride_enters_searching() -> None:
    ride = _new_ride()
    assert ride.status is RideStatus.SEARCHING


def test_new_ride_has_no_driver_or_vehicle_assigned() -> None:
    ride = _new_ride()
    assert ride.driver_id is None
    assert ride.vehicle_id is None


def test_new_ride_has_no_fare_quote() -> None:
    """ADR-0010 Decision 1: Task 3.1 never calculates a fare."""
    ride = _new_ride()
    assert ride.active_fare_quote_id is None


def test_new_ride_current_location_matches_original_at_creation() -> None:
    ride = _new_ride()
    assert ride.current_pickup == ride.original_pickup
    assert ride.current_destination == ride.original_destination


def test_new_ride_generates_unique_ids() -> None:
    first = _new_ride()
    second = _new_ride()
    assert first.id != second.id


def test_new_ride_belongs_to_the_given_customer() -> None:
    ride = _new_ride()
    assert ride.customer_id == CUSTOMER_ID


def test_new_ride_persists_requested_vehicle_category() -> None:
    """ADR-0011 Decision 1: added Phase 3 / Task 3.2."""
    ride = _new_ride(vehicle_category="AUTO")
    assert ride.requested_vehicle_category is VehicleCategory.AUTO


def test_new_ride_rejects_unknown_vehicle_category() -> None:
    with pytest.raises(InvalidCategoryError):
        _new_ride(vehicle_category="TRUCK")


def test_new_ride_persists_requested_cab_tier() -> None:
    """ADR-0020 Decision 1."""
    ride = _new_ride(vehicle_category="CAB", cab_tier="PREMIUM")
    assert ride.requested_cab_tier is not None
    assert ride.requested_cab_tier.value == "PREMIUM"


def test_new_ride_requesting_cab_without_a_tier_is_rejected() -> None:
    with pytest.raises(InvalidCabTierError):
        _new_ride(vehicle_category="CAB", cab_tier=None)


def test_new_ride_requesting_auto_has_no_cab_tier() -> None:
    ride = _new_ride(vehicle_category="AUTO")
    assert ride.requested_cab_tier is None


def test_new_ride_requesting_auto_with_a_tier_is_rejected() -> None:
    with pytest.raises(InvalidCabTierError):
        _new_ride(vehicle_category="AUTO", cab_tier="ECO")


@pytest.mark.parametrize("bad_latitude", [-90.1, 90.1, 1000.0, -1000.0])
def test_invalid_pickup_latitude_is_rejected(bad_latitude: float) -> None:
    with pytest.raises(InvalidCoordinateError):
        _new_ride(pickup_latitude=bad_latitude)


@pytest.mark.parametrize("bad_longitude", [-180.1, 180.1, 1000.0, -1000.0])
def test_invalid_pickup_longitude_is_rejected(bad_longitude: float) -> None:
    with pytest.raises(InvalidCoordinateError):
        _new_ride(pickup_longitude=bad_longitude)


@pytest.mark.parametrize("bad_latitude", [-90.1, 90.1])
def test_invalid_destination_latitude_is_rejected(bad_latitude: float) -> None:
    with pytest.raises(InvalidCoordinateError):
        _new_ride(destination_latitude=bad_latitude)


@pytest.mark.parametrize("bad_longitude", [-180.1, 180.1])
def test_invalid_destination_longitude_is_rejected(bad_longitude: float) -> None:
    with pytest.raises(InvalidCoordinateError):
        _new_ride(destination_longitude=bad_longitude)


@pytest.mark.parametrize("boundary", [-90.0, 90.0])
def test_boundary_latitude_values_are_accepted(boundary: float) -> None:
    ride = _new_ride(pickup_latitude=boundary)
    assert ride.original_pickup.latitude == boundary


def test_same_pickup_and_destination_is_allowed() -> None:
    """No same-location restriction is documented anywhere — none is
    invented (ADR-0010 discussion, Task 3.1 plan item G)."""
    ride = _new_ride(
        destination_latitude=25.5941,
        destination_longitude=85.1376,
    )
    assert ride.original_pickup == ride.original_destination


def test_validate_coordinates_returns_the_given_values() -> None:
    coordinates = validate_coordinates(12.34, 56.78, field_name="pickup")
    assert coordinates.latitude == 12.34
    assert coordinates.longitude == 56.78


# --- Schedule a Ride & Book for Someone Else (ADR-0057) -----------------


def test_new_ride_with_no_scheduled_for_enters_searching_unchanged() -> None:
    ride = _new_ride()
    assert ride.status is RideStatus.SEARCHING
    assert ride.scheduled_for is None
    assert ride.lock_in_at is None


def test_new_ride_with_a_valid_scheduled_for_enters_scheduled() -> None:
    scheduled_for = NOW + timedelta(hours=2)
    ride = _new_ride(scheduled_for=scheduled_for)
    assert ride.status is RideStatus.SCHEDULED
    assert ride.scheduled_for == scheduled_for
    assert ride.lock_in_at == scheduled_for - SCHEDULED_RIDE_LOCK_IN_WINDOW


@pytest.mark.parametrize(
    "lead_time",
    [timedelta(minutes=59), timedelta(hours=24, minutes=1), timedelta(minutes=-5)],
)
def test_new_ride_rejects_a_scheduled_for_outside_the_1_to_24_hour_window(
    lead_time: timedelta,
) -> None:
    with pytest.raises(InvalidScheduledForError):
        _new_ride(scheduled_for=NOW + lead_time)


@pytest.mark.parametrize("lead_time", [timedelta(hours=1), timedelta(hours=24)])
def test_new_ride_accepts_the_exact_window_boundaries(lead_time: timedelta) -> None:
    ride = _new_ride(scheduled_for=NOW + lead_time)
    assert ride.status is RideStatus.SCHEDULED


def test_validate_scheduled_for_returns_searching_for_none() -> None:
    status, lock_in_at = validate_scheduled_for(None, now=NOW)
    assert status is RideStatus.SEARCHING
    assert lock_in_at is None


def test_new_ride_with_no_linked_contact_is_unchanged() -> None:
    ride = _new_ride()
    assert ride.linked_contact_name is None
    assert ride.linked_contact_phone is None


def test_new_ride_with_a_valid_linked_contact_persists_both_fields() -> None:
    ride = _new_ride(
        linked_contact_name="Priya Singh", linked_contact_phone="9999999999"
    )
    assert ride.linked_contact_name == "Priya Singh"
    # Normalized to E.164 (modules.identity.domain.phone_number).
    assert ride.linked_contact_phone == "+919999999999"


def test_new_ride_rejects_a_linked_contact_name_with_no_phone() -> None:
    with pytest.raises(InvalidLinkedContactError):
        _new_ride(linked_contact_name="Priya Singh", linked_contact_phone=None)


def test_new_ride_rejects_a_linked_contact_phone_with_no_name() -> None:
    with pytest.raises(InvalidLinkedContactError):
        _new_ride(linked_contact_name=None, linked_contact_phone="9999999999")


def test_new_ride_rejects_a_blank_linked_contact_name() -> None:
    with pytest.raises(InvalidLinkedContactError):
        _new_ride(linked_contact_name="   ", linked_contact_phone="9999999999")


def test_new_ride_rejects_an_invalid_linked_contact_phone() -> None:
    with pytest.raises(InvalidLinkedContactError):
        _new_ride(linked_contact_name="Priya Singh", linked_contact_phone="not-a-phone")


def test_validate_linked_contact_returns_none_none_for_no_contact() -> None:
    assert validate_linked_contact(None, None) == (None, None)
