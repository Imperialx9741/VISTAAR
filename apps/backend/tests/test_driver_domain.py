"""Unit tests for the pure Driver domain layer (no DB/HTTP)."""

import pytest

from modules.driver.domain.entities import (
    Driver,
    validate_full_name,
    validate_profile_photo_uri,
)
from modules.driver.domain.errors import (
    InvalidFullNameError,
    InvalidProfilePhotoUriError,
)


class TestFullNameValidation:
    def test_valid_name_is_trimmed(self) -> None:
        assert validate_full_name("  Ravi Kumar  ") == "Ravi Kumar"

    def test_blank_after_strip_is_rejected(self) -> None:
        with pytest.raises(InvalidFullNameError):
            validate_full_name("   ")

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidFullNameError):
            validate_full_name("x" * 151)

    def test_exactly_max_length_is_allowed(self) -> None:
        assert validate_full_name("x" * 150) == "x" * 150


class TestProfilePhotoUriValidation:
    def test_none_is_allowed(self) -> None:
        assert validate_profile_photo_uri(None) is None

    def test_valid_uri_is_trimmed(self) -> None:
        assert validate_profile_photo_uri("  ref-123  ") == "ref-123"

    def test_blank_is_rejected(self) -> None:
        with pytest.raises(InvalidProfilePhotoUriError):
            validate_profile_photo_uri("   ")


class TestDriverNew:
    def test_defaults_match_documented_schema(self) -> None:
        import uuid
        from datetime import UTC, datetime

        driver = Driver.new(uuid.uuid4(), full_name="Ravi Kumar", now=datetime.now(UTC))

        assert driver.full_name == "Ravi Kumar"
        assert driver.profile_photo_uri is None
        assert driver.verification_status.value == "PENDING"
        assert driver.operational_status.value == "OFFLINE"
        assert driver.strikes == 0

    def test_blank_full_name_is_rejected_at_creation(self) -> None:
        import uuid
        from datetime import UTC, datetime

        with pytest.raises(InvalidFullNameError):
            Driver.new(uuid.uuid4(), full_name="   ", now=datetime.now(UTC))
