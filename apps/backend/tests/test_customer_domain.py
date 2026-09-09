"""Unit tests for the pure Customer domain layer (no DB/HTTP)."""

import pytest

from modules.customer.domain.entities import (
    validate_full_name,
    validate_language,
    validate_profile_photo_uri,
)
from modules.customer.domain.errors import (
    InvalidFullNameError,
    InvalidLanguageError,
    InvalidProfilePhotoUriError,
)


class TestFullNameValidation:
    def test_none_is_allowed(self) -> None:
        assert validate_full_name(None) is None

    def test_valid_name_is_trimmed(self) -> None:
        assert validate_full_name("  Jane Doe  ") == "Jane Doe"

    def test_blank_after_strip_is_rejected(self) -> None:
        with pytest.raises(InvalidFullNameError):
            validate_full_name("   ")

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidFullNameError):
            validate_full_name("x" * 151)

    def test_exactly_max_length_is_allowed(self) -> None:
        assert validate_full_name("x" * 150) == "x" * 150


class TestLanguageValidation:
    def test_none_is_allowed(self) -> None:
        assert validate_language(None) is None

    def test_english_is_allowed(self) -> None:
        assert validate_language("en") == "en"

    def test_hindi_is_allowed(self) -> None:
        assert validate_language("hi") == "hi"

    def test_case_is_normalized(self) -> None:
        assert validate_language("EN") == "en"

    def test_unsupported_language_is_rejected(self) -> None:
        with pytest.raises(InvalidLanguageError):
            validate_language("fr")


class TestProfilePhotoUriValidation:
    def test_none_is_allowed(self) -> None:
        assert validate_profile_photo_uri(None) is None

    def test_valid_uri_is_trimmed(self) -> None:
        assert validate_profile_photo_uri("  ref-123  ") == "ref-123"

    def test_blank_is_rejected(self) -> None:
        with pytest.raises(InvalidProfilePhotoUriError):
            validate_profile_photo_uri("   ")

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(InvalidProfilePhotoUriError):
            validate_profile_photo_uri("x" * 2049)
