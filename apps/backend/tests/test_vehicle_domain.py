"""Unit tests for the pure Vehicle domain layer (no DB/HTTP)."""

import uuid
from datetime import UTC, datetime

import pytest

from modules.vehicle.domain.entities import (
    Vehicle,
    VehicleCategory,
    matching_category_key,
    validate_cab_tier,
    validate_category,
    validate_make_or_model,
    validate_registration_number,
)
from modules.vehicle.domain.errors import (
    InvalidCabTierError,
    InvalidCategoryError,
    InvalidMakeOrModelError,
    InvalidRegistrationNumberError,
)


class TestCategoryValidation:
    @pytest.mark.parametrize("category", ["BIKE", "AUTO", "CAB"])
    def test_documented_categories_are_allowed(self, category: str) -> None:
        assert validate_category(category).value == category

    def test_undocumented_category_is_rejected(self) -> None:
        with pytest.raises(InvalidCategoryError):
            validate_category("TRUCK")


class TestRegistrationNumberValidation:
    def test_valid_number_is_uppercased_and_trimmed(self) -> None:
        assert validate_registration_number("  br01ab1234  ") == "BR01AB1234"

    def test_blank_is_rejected(self) -> None:
        with pytest.raises(InvalidRegistrationNumberError):
            validate_registration_number("   ")

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidRegistrationNumberError):
            validate_registration_number("x" * 31)


class TestMakeOrModelValidation:
    def test_none_is_allowed(self) -> None:
        assert validate_make_or_model(None, field_name="make") is None

    def test_blank_normalizes_to_none(self) -> None:
        assert validate_make_or_model("   ", field_name="make") is None

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidMakeOrModelError):
            validate_make_or_model("x" * 101, field_name="model")


class TestCabTierValidation:
    """ADR-0020 Decision 1."""

    @pytest.mark.parametrize("tier", ["ECO", "PREMIUM", "PREMIUM_PLUS"])
    def test_cab_accepts_every_documented_tier(self, tier: str) -> None:
        result = validate_cab_tier(VehicleCategory.CAB, tier)
        assert result is not None
        assert result.value == tier

    def test_cab_without_a_tier_is_rejected(self) -> None:
        with pytest.raises(InvalidCabTierError):
            validate_cab_tier(VehicleCategory.CAB, None)

    def test_cab_with_an_unknown_tier_is_rejected(self) -> None:
        with pytest.raises(InvalidCabTierError):
            validate_cab_tier(VehicleCategory.CAB, "LUXURY")

    @pytest.mark.parametrize("category", [VehicleCategory.BIKE, VehicleCategory.AUTO])
    def test_non_cab_without_a_tier_is_fine(self, category: VehicleCategory) -> None:
        assert validate_cab_tier(category, None) is None

    @pytest.mark.parametrize("category", [VehicleCategory.BIKE, VehicleCategory.AUTO])
    def test_non_cab_with_a_tier_is_rejected(self, category: VehicleCategory) -> None:
        with pytest.raises(InvalidCabTierError):
            validate_cab_tier(category, "ECO")


class TestMatchingCategoryKey:
    """ADR-0020 Decision 1."""

    def test_cab_composes_tier_into_the_key(self) -> None:
        assert (
            matching_category_key(
                VehicleCategory.CAB, validate_cab_tier(VehicleCategory.CAB, "ECO")
            )
            == "CAB:ECO"
        )

    def test_bike_and_auto_are_unchanged(self) -> None:
        assert matching_category_key(VehicleCategory.BIKE, None) == "BIKE"
        assert matching_category_key(VehicleCategory.AUTO, None) == "AUTO"


class TestVehicleNew:
    def test_defaults_match_documented_schema(self) -> None:
        vehicle = Vehicle.new(
            driver_id=uuid.uuid4(),
            category="CAB",
            cab_tier="ECO",
            registration_number="BR01AB1234",
            make="Maruti",
            model="Dzire",
            now=datetime.now(UTC),
        )

        assert vehicle.category.value == "CAB"
        assert vehicle.cab_tier is not None
        assert vehicle.cab_tier.value == "ECO"
        assert vehicle.registration_number == "BR01AB1234"
        assert vehicle.verification_status.value == "PENDING"
        assert vehicle.operational_status.value == "INACTIVE"

    def test_bike_has_no_cab_tier(self) -> None:
        vehicle = Vehicle.new(
            driver_id=uuid.uuid4(),
            category="BIKE",
            registration_number="BR01AB5678",
            make=None,
            model=None,
            now=datetime.now(UTC),
        )

        assert vehicle.cab_tier is None
