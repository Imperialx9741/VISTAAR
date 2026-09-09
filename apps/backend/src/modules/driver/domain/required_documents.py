"""Required-document validation for admin approval.

Phase 2 / Task 2.6C — enforces business-rules.md BR-123 for drivers. The
required set below is derived from BR-097/PRD.md §9's "Identity"
onboarding fields (Government ID, Driving licence) — the only driver
document types with an inherent legal-validity concept, same reasoning
that excludes an equivalent "photo" item on the vehicle side
(modules/vehicle/domain/required_documents.py). Carries the same
"subject to final compliance review" caveat BR-097 itself states — not a
final, regulator-reviewed KYC list.
"""

from __future__ import annotations

from datetime import datetime

from modules.driver.domain.entities import DocumentVerificationStatus, DriverDocument

# BR-123's required driver document set (Task 2.6C).
REQUIRED_DRIVER_DOCUMENT_TYPES = frozenset({"GOVERNMENT_ID", "DRIVING_LICENSE"})


def missing_or_invalid_required_documents(
    documents: list[DriverDocument], *, now: datetime
) -> list[str]:
    """Returns the required document_types with no APPROVED, unexpired
    document on file — an empty list means every required document is
    valid. A document counts as valid only if
    verification_status == APPROVED and (expires_at is None or
    expires_at is in the future) — PENDING/REJECTED/EXPIRED/missing all
    count as invalid, per BR-123."""
    invalid: list[str] = []
    for required_type in sorted(REQUIRED_DRIVER_DOCUMENT_TYPES):
        matching = [d for d in documents if d.document_type == required_type]
        has_valid = any(
            d.verification_status is DocumentVerificationStatus.APPROVED
            and (d.expires_at is None or d.expires_at > now)
            for d in matching
        )
        if not has_valid:
            invalid.append(required_type)
    return invalid
