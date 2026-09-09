"""SQLAlchemy-backed implementation of VerificationCaseRepository.

Translates between the ORM row (models.py) and the pure domain entity
(domain/entities.py) — mirrors the other modules' repositories.py role.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from modules.verification.domain.entities import (
    Evidence,
    VerificationCase,
    VerificationOutcome,
    VerificationResult,
    VerificationStatus,
    VerificationType,
)
from modules.verification.models import (
    VerificationCaseORM,
    VerificationEvidenceORM,
    VerificationResultORM,
)


def _case_from_orm(row: VerificationCaseORM) -> VerificationCase:
    return VerificationCase(
        id=row.id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        verification_type=VerificationType(row.verification_type),
        status=VerificationStatus(row.status),
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _evidence_from_orm(row: VerificationEvidenceORM) -> Evidence:
    return Evidence(
        id=row.id,
        case_id=row.case_id,
        evidence_uri=row.evidence_uri,
        metadata=row.metadata_,
        created_at=row.created_at,
    )


def _result_from_orm(row: VerificationResultORM) -> VerificationResult:
    return VerificationResult(
        id=row.id,
        case_id=row.case_id,
        result=VerificationOutcome(row.result),
        confidence=float(row.confidence) if row.confidence is not None else None,
        model_name=row.model_name,
        reviewer_id=row.reviewer_id,
        reason=row.reason,
        created_at=row.created_at,
    )


class SqlAlchemyVerificationCaseRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create_case(self, case: VerificationCase) -> VerificationCase:
        row = VerificationCaseORM(
            id=case.id,
            subject_type=case.subject_type,
            subject_id=case.subject_id,
            verification_type=case.verification_type.value,
            status=case.status.value,
            completed_at=case.completed_at,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _case_from_orm(row)

    def get_case(self, case_id: uuid.UUID) -> VerificationCase | None:
        row = self._db.get(VerificationCaseORM, case_id)
        return _case_from_orm(row) if row else None

    def list_cases_for_subject(
        self, *, subject_type: str, subject_id: uuid.UUID
    ) -> list[VerificationCase]:
        rows = (
            self._db.execute(
                select(VerificationCaseORM)
                .where(
                    VerificationCaseORM.subject_type == subject_type,
                    VerificationCaseORM.subject_id == subject_id,
                )
                .order_by(VerificationCaseORM.created_at)
            )
            .scalars()
            .all()
        )
        return [_case_from_orm(row) for row in rows]

    def list_by_status(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[VerificationCase], int]:
        filters = []
        if status:
            filters.append(VerificationCaseORM.status == status)

        total = self._db.execute(
            select(func.count()).select_from(VerificationCaseORM).where(*filters)
        ).scalar_one()
        rows = (
            self._db.execute(
                select(VerificationCaseORM)
                .where(*filters)
                .order_by(VerificationCaseORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_case_from_orm(row) for row in rows], total

    def save_case(self, case: VerificationCase) -> None:
        row = self._db.get(VerificationCaseORM, case.id)
        if row is None:
            raise LookupError(f"Verification case {case.id} not found")

        row.status = case.status.value
        row.completed_at = case.completed_at
        self._db.flush()
        self._db.refresh(row)

    def add_evidence(self, evidence: Evidence) -> Evidence:
        row = VerificationEvidenceORM(
            id=evidence.id,
            case_id=evidence.case_id,
            evidence_uri=evidence.evidence_uri,
            metadata_=evidence.metadata,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _evidence_from_orm(row)

    def list_evidence_for_case(self, case_id: uuid.UUID) -> list[Evidence]:
        rows = (
            self._db.execute(
                select(VerificationEvidenceORM)
                .where(VerificationEvidenceORM.case_id == case_id)
                .order_by(VerificationEvidenceORM.created_at)
            )
            .scalars()
            .all()
        )
        return [_evidence_from_orm(row) for row in rows]

    def add_result(self, result: VerificationResult) -> VerificationResult:
        row = VerificationResultORM(
            id=result.id,
            case_id=result.case_id,
            result=result.result.value,
            confidence=result.confidence,
            model_name=result.model_name,
            reviewer_id=result.reviewer_id,
            reason=result.reason,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _result_from_orm(row)
