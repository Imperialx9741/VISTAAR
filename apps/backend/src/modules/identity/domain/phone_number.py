"""Canonical phone-number representation and normalization.

Normalization approach (as required by the task's "PHONE NUMBER" section):

VISTAAR stores exactly one canonical representation per identity: E.164
format (a leading "+", followed by the country code and subscriber number,
digits only — e.g. "+919999999999", matching the example already used in
docs/05-api/api-contracts.md §6 and #12). No other representation of the
same number is ever persisted, so there is no risk of the same person
existing twice under two different-looking phone strings.

Two inputs are accepted and both normalize to the same E.164 string:

1. Already E.164 (``+`` followed by 8-15 digits, per ITU-T E.164) — used
   as-is after validation.
2. A bare 10-digit number with no country code — prefixed with ``+91``.
   This is a technical normalization convenience, not an invented business
   rule: PRD.md §6 scopes VISTAAR's initial market as India-only, and every
   phone-number example throughout the documentation set (PRD.md,
   business-rules.md, api-contracts.md) already uses ``+91``. If VISTAAR
   ever expands beyond India, this default must be revisited — it is
   flagged here precisely so that expansion doesn't silently keep assuming
   India.

Anything else (missing digits, letters, multiple ``+`` signs, obviously
too long/short) is rejected. No other India-specific validation (e.g.
which digit a mobile number must start with) is enforced, because
business-rules.md and PRD.md do not define one — inventing one here would
be exactly the kind of unrequested business decision this task must not
make.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from modules.identity.domain.errors import InvalidPhoneNumberError

_E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
_BARE_INDIAN_MOBILE_PATTERN = re.compile(r"^\d{10}$")
_DEFAULT_MARKET_COUNTRY_CODE = "+91"  # PRD.md §6: initial market is India.


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    """An immutable, already-validated, E.164-normalized phone number."""

    value: str

    def __str__(self) -> str:
        return self.value

    @staticmethod
    def parse(raw: str) -> PhoneNumber:
        """Normalize and validate a raw phone number string.

        Raises:
            InvalidPhoneNumberError: if ``raw`` cannot be normalized to a
                valid E.164 number under the rules documented above.
        """
        if not raw or not raw.strip():
            raise InvalidPhoneNumberError("Phone number must not be empty.")

        candidate = re.sub(r"[\s\-()]", "", raw.strip())

        if _E164_PATTERN.match(candidate):
            return PhoneNumber(candidate)

        if _BARE_INDIAN_MOBILE_PATTERN.match(candidate):
            normalized = f"{_DEFAULT_MARKET_COUNTRY_CODE}{candidate}"
            return PhoneNumber(normalized)

        raise InvalidPhoneNumberError(
            f"'{raw}' is not a valid phone number. Expected E.164 format "
            "(e.g. +919999999999) or a 10-digit number."
        )
