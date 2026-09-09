"""Verification domain entities.

Field shapes match docs/04-database/database-design.md §27
(verification.cases / verification.evidence / verification.results)
exactly. See docs/14-decisions/ADR-0008-verification-case-scope-and-open-items.md
for the design decisions this module implements.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class VerificationStatus(StrEnum):
    """Exactly docs/07-state-machines/state-machines.md §43's ("Verification
    State Machine") 6 documented states. This is a case's full lifecycle
    status — distinct from a single verification *result* (see
    VerificationOutcome below) and distinct from
    driver.documents.verification_status/vehicle.documents.verification_status
    (state-machines.md §44's separate PENDING/APPROVED/REJECTED/EXPIRED
    model). No automatic write-back exists between the two — see ADR-0008
    item 5."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    EXPIRED = "EXPIRED"


class VerificationType(StrEnum):
    """Exactly docs/04-domain-design/domain-design.md §18.2's documented
    "Verification Types". This module only ever constructs
    DRIVER_DOCUMENT/VEHICLE_DOCUMENT cases (Phase 2 / Task 2.6).
    PARKING_PROOF belongs to the Ride domain's not-yet-built flow —
    included here only because it is part of the documented enum, never
    constructed by this module."""

    DRIVER_DOCUMENT = "DRIVER_DOCUMENT"
    VEHICLE_DOCUMENT = "VEHICLE_DOCUMENT"
    PARKING_PROOF = "PARKING_PROOF"


class VerificationOutcome(StrEnum):
    """The subset of VerificationStatus a single verification *result* can
    produce (state-machines.md §43: "Normal: ...→ APPROVED", "Failure:
    ...→ REJECTED", "Low confidence: ...→ MANUAL_REVIEW"). Distinct from
    VerificationStatus because PENDING/PROCESSING/EXPIRED are case-level
    states a result never directly produces."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass(slots=True)
class VerificationCase:
    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    verification_type: VerificationType
    status: VerificationStatus
    created_at: datetime
    completed_at: datetime | None

    @staticmethod
    def new(
        *,
        subject_type: str,
        subject_id: uuid.UUID,
        verification_type: VerificationType,
        now: datetime,
    ) -> VerificationCase:
        return VerificationCase(
            id=uuid.uuid4(),
            subject_type=subject_type,
            subject_id=subject_id,
            verification_type=verification_type,
            status=VerificationStatus.PENDING,
            created_at=now,
            completed_at=None,
        )


@dataclass(slots=True)
class Evidence:
    id: uuid.UUID
    case_id: uuid.UUID
    evidence_uri: str
    metadata: dict[str, object] | None
    created_at: datetime

    @staticmethod
    def new(
        *,
        case_id: uuid.UUID,
        evidence_uri: str,
        metadata: dict[str, object] | None,
        now: datetime,
    ) -> Evidence:
        return Evidence(
            id=uuid.uuid4(),
            case_id=case_id,
            evidence_uri=evidence_uri,
            metadata=metadata,
            created_at=now,
        )


@dataclass(slots=True)
class VerificationResult:
    id: uuid.UUID
    case_id: uuid.UUID
    result: VerificationOutcome
    confidence: float | None
    model_name: str | None
    reviewer_id: uuid.UUID | None
    reason: str | None
    created_at: datetime

    @staticmethod
    def new(
        *,
        case_id: uuid.UUID,
        result: VerificationOutcome,
        confidence: float | None,
        model_name: str | None,
        reviewer_id: uuid.UUID | None,
        reason: str | None,
        now: datetime,
    ) -> VerificationResult:
        return VerificationResult(
            id=uuid.uuid4(),
            case_id=case_id,
            result=result,
            confidence=confidence,
            model_name=model_name,
            reviewer_id=reviewer_id,
            reason=reason,
            created_at=now,
        )
