"""Required-document validation for admin approval.

Phase 2 / Task 2.6C — enforces business-rules.md BR-123 for vehicles.
The required set below is derived from BR-097/PRD.md §9's "Vehicle"
onboarding fields (RC, Insurance) — the only vehicle document types with
an inherent legal-validity concept. VEHICLE_PHOTO is deliberately
excluded: no authoritative source states a photo needs to reach an
approved/valid verification state before admin approval — unlike RC/
Insurance, a photo has no natural expiry or legal-validity concept, and
BR-097 lists it as an onboarding item, not a verification-gated document.
See docs/14-decisions/ADR-0009 point C for the full reasoning; this is
recorded as a considered decision, not an oversight. vehicle_category and
registration_number are vehicle.vehicles fields (Task 2.4), not
documents, and are excluded from this list for that reason.
"""

from __future__ import annotations

from datetime import datetime

from modules.vehicle.domain.entities import DocumentVerificationStatus, VehicleDocument

# BR-123's required vehicle document set (Task 2.6C).
REQUIRED_VEHICLE_DOCUMENT_TYPES = frozenset({"RC", "INSURANCE"})


def missing_or_invalid_required_documents(
    documents: list[VehicleDocument], *, now: datetime
) -> list[str]:
    """Mirrors modules.driver.domain.required_documents's function
    exactly — see that module's docstring for the validity rule."""
    invalid: list[str] = []
    for required_type in sorted(REQUIRED_VEHICLE_DOCUMENT_TYPES):
        matching = [d for d in documents if d.document_type == required_type]
        has_valid = any(
            d.verification_status is DocumentVerificationStatus.APPROVED
            and (d.expires_at is None or d.expires_at > now)
            for d in matching
        )
        if not has_valid:
            invalid.append(required_type)
    return invalid
