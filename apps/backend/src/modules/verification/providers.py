"""Verification provider adapters.

No production verification provider is integrated here (ADR-0008 item 7:
"Verification provider remains unresolved"; business-rules.md §43 lists
"Verification provider" as an explicitly unfinalized item). Only a
manual-review default exists — the same "explicit stub, no real
integration" precedent as modules.identity.sms.DevConsoleSmsProvider.
``get_verification_provider()`` is the single place a real provider will
be wired in later, behind the same ``VerificationProvider`` protocol — no
call site elsewhere in this module will need to change.
"""

from __future__ import annotations

from typing import Protocol

from modules.verification.domain.entities import (
    Evidence,
    VerificationCase,
    VerificationOutcome,
)


class VerificationProvider(Protocol):
    async def verify(
        self, case: VerificationCase, evidence: Evidence
    ) -> VerificationOutcome: ...


class ManualReviewVerificationProvider:
    """Always routes to manual review.

    Per technical-architecture.md §40 ("AI must not bypass required human
    review for ambiguous or high-risk evidence") and ADR-0008 item 6: with
    no approved AI/authoritative provider, the only architecture-consistent
    default is to never auto-approve or auto-reject — everything defers to
    a human. This is intentionally the ONLY provider implementation; see
    ADR-0008 item 7 for why no real provider is selected yet.
    """

    async def verify(
        self, case: VerificationCase, evidence: Evidence
    ) -> VerificationOutcome:
        return VerificationOutcome.MANUAL_REVIEW


def get_verification_provider() -> ManualReviewVerificationProvider:
    """Factory for the configured verification provider.

    Unconditional — unlike modules.identity.sms.get_sms_provider(), there
    is no settings-driven branch yet, because no second implementation
    exists to select between (ADR-0008 item 7)."""
    return ManualReviewVerificationProvider()
