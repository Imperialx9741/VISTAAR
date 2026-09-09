"""Unit tests for the pure Identity domain layer (no DB/Redis/HTTP)."""

import pytest

from modules.identity.domain.errors import InvalidPhoneNumberError
from modules.identity.domain.otp import generate_numeric_otp, hash_otp, verify_otp
from modules.identity.domain.phone_number import PhoneNumber


class TestPhoneNumberNormalization:
    def test_already_e164_is_used_as_is(self) -> None:
        assert PhoneNumber.parse("+919999999999").value == "+919999999999"

    def test_bare_ten_digit_number_gets_india_default(self) -> None:
        assert PhoneNumber.parse("9999999999").value == "+919999999999"

    def test_whitespace_and_punctuation_are_stripped(self) -> None:
        assert PhoneNumber.parse(" +91 9999-999-999 ").value == "+919999999999"

    def test_same_number_normalizes_identically_both_ways(self) -> None:
        a = PhoneNumber.parse("+919999999999")
        b = PhoneNumber.parse("9999999999")
        assert a.value == b.value

    @pytest.mark.parametrize(
        "raw",
        ["", "   ", "abcdefghij", "12345", "+91", "++919999999999", "0" * 20],
    )
    def test_invalid_numbers_are_rejected(self, raw: str) -> None:
        with pytest.raises(InvalidPhoneNumberError):
            PhoneNumber.parse(raw)


class TestOtpGeneration:
    def test_generates_numeric_string_of_requested_length(self) -> None:
        otp = generate_numeric_otp(6)
        assert len(otp) == 6
        assert otp.isdigit()

    def test_generated_otps_are_not_trivially_predictable(self) -> None:
        # Not a rigorous randomness test, but guards against an accidental
        # constant/sequential generator.
        samples = {generate_numeric_otp(6) for _ in range(50)}
        assert len(samples) > 40


class TestOtpHashing:
    def test_correct_otp_verifies(self) -> None:
        h = hash_otp("123456", pepper="pepper")
        assert verify_otp("123456", pepper="pepper", expected_hash=h) is True

    def test_incorrect_otp_does_not_verify(self) -> None:
        h = hash_otp("123456", pepper="pepper")
        assert verify_otp("000000", pepper="pepper", expected_hash=h) is False

    def test_hash_is_not_the_plaintext_otp(self) -> None:
        h = hash_otp("123456", pepper="pepper")
        assert h != "123456"

    def test_different_pepper_fails_verification(self) -> None:
        h = hash_otp("123456", pepper="pepper-a")
        assert verify_otp("123456", pepper="pepper-b", expected_hash=h) is False
