"""Integration tests: real Postgres session, exercising
VerificationService + SqlAlchemyVerificationCaseRepository end-to-end,
including the "vehicle documents participate at the service layer only"
behavior from ADR-0008 item 3 — proven here since no HTTP route composes
it automatically (see modules/verification/__init__.py).

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from _integration_db import truncate_integration_tables
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession

from core.database import SessionLocal, engine
from modules.driver.models import DriverORM
from modules.driver.repositories import SqlAlchemyDriverDocumentRepository
from modules.driver.service import DriverDocumentService
from modules.identity.models import AccountORM
from modules.vehicle.domain.entities import VehicleDocument
from modules.vehicle.models import VehicleORM
from modules.vehicle.repositories import SqlAlchemyVehicleDocumentRepository
from modules.vehicle.service import VehicleDocumentService
from modules.verification.domain.entities import VerificationOutcome, VerificationType
from modules.verification.providers import ManualReviewVerificationProvider
from modules.verification.repositories import SqlAlchemyVerificationCaseRepository
from modules.verification.service import VerificationService


def _infra_available() -> bool:
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except OperationalError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _infra_available(),
    reason="Postgres is offline/unreachable (start docker-compose.dev.yml)",
)


@pytest.fixture(autouse=True)
def _clean_integration_tables() -> None:
    """Task 2.7B test-isolation correction: wipe the tables this file
    writes to before every test — see the identical fixture and its
    docstring in test_vehicle_document_integration.py for the rationale.
    Local to this file only; not applied suite-wide."""
    truncate_integration_tables(engine)


@pytest.fixture
def db() -> Generator[DbSession, None, None]:
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def service(db: DbSession) -> VerificationService:
    return VerificationService(
        cases=SqlAlchemyVerificationCaseRepository(db),
        provider=ManualReviewVerificationProvider(),
    )


def _random_phone() -> str:
    return "+91" + "".join(str(secrets.randbelow(10)) for _ in range(10))


def _create_driver_id(db: DbSession) -> uuid.UUID:
    account = AccountORM(account_type="DRIVER", phone=_random_phone())
    db.add(account)
    db.flush()
    driver = DriverORM(id=account.id, full_name="Ravi Kumar")
    db.add(driver)
    db.flush()
    db.commit()
    return driver.id


def _create_vehicle_id(db: DbSession) -> uuid.UUID:
    account = AccountORM(account_type="DRIVER", phone=_random_phone())
    db.add(account)
    db.flush()
    driver = DriverORM(id=account.id, full_name="Ravi Kumar")
    db.add(driver)
    db.flush()
    vehicle = VehicleORM(
        driver_id=driver.id,
        category="CAB",
        # UUID-derived (122 bits of randomness) rather than a 9,999-value
        # range — see test_vehicle_document_integration.py's identical
        # fixture for why the old narrow range was able to collide.
        registration_number="BR01AB" + uuid.uuid4().hex[:16].upper(),
    )
    db.add(vehicle)
    db.flush()
    db.commit()
    return vehicle.id


def test_submit_evidence_persists_case_and_evidence(
    db: DbSession, service: VerificationService
) -> None:
    document_id = uuid.uuid4()

    case = service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=document_id,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )
    db.commit()

    case_row = db.execute(
        text("SELECT status, subject_type FROM verification.cases WHERE id = :id"),
        {"id": str(case.id)},
    ).fetchone()
    assert case_row is not None
    assert case_row[0] == "PENDING"
    assert case_row[1] == "DRIVER_DOCUMENT"

    evidence_row = db.execute(
        text("SELECT evidence_uri FROM verification.evidence WHERE case_id = :id"),
        {"id": str(case.id)},
    ).fetchone()
    assert evidence_row is not None
    assert evidence_row[0] == "ref-1"


def test_vehicle_document_can_submit_evidence_via_service_layer(
    db: DbSession, service: VerificationService
) -> None:
    """ADR-0008 item 3: vehicle documents participate through the same
    VerificationService, called directly here since no HTTP endpoint
    exists for vehicle documents (ADR-0007) — this test stands in for the
    future caller that would compose this the same way
    modules/driver/router.py already does."""
    vehicle_id = _create_vehicle_id(db)
    document = VehicleDocument.new(
        vehicle_id=vehicle_id,
        document_type="insurance",
        document_number="POL-1",
        evidence_uri="ref-vehicle-1",
        expires_at=None,
        now=datetime.now(UTC),
    )

    # Same evidence-presence rule as the driver path (ADR-0008 item 9):
    # only submit_evidence() when evidence_uri is present.
    assert document.evidence_uri is not None
    case = service.submit_evidence(
        subject_type="VEHICLE_DOCUMENT",
        subject_id=document.id,
        verification_type=VerificationType.VEHICLE_DOCUMENT,
        evidence_uri=document.evidence_uri,
    )
    db.commit()

    case_row = db.execute(
        text("SELECT subject_type, subject_id FROM verification.cases WHERE id = :id"),
        {"id": str(case.id)},
    ).fetchone()
    assert case_row is not None
    assert case_row[0] == "VEHICLE_DOCUMENT"
    assert case_row[1] == document.id


def test_vehicle_document_without_evidence_uri_creates_no_case(
    service: VerificationService,
) -> None:
    """Same evidence-presence rule: a document created without
    evidence_uri never reaches submit_evidence() at all — no case, no
    evidence row, nothing to assert against because nothing is called."""
    document = VehicleDocument.new(
        vehicle_id=uuid.uuid4(),
        document_type="insurance",
        document_number="POL-1",
        evidence_uri=None,
        expires_at=None,
        now=datetime.now(UTC),
    )

    assert document.evidence_uri is None
    cases = service.list_cases_for_subject(
        subject_type="VEHICLE_DOCUMENT", subject_id=document.id
    )
    assert cases == []


@pytest.mark.anyio
async def test_run_verification_persists_result_and_transitions_case(
    db: DbSession, service: VerificationService
) -> None:
    case = service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=uuid.uuid4(),
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )
    db.commit()

    updated = await service.run_verification(case_id=case.id)
    db.commit()

    assert updated.status.value == "MANUAL_REVIEW"
    result_row = db.execute(
        text("SELECT result, model_name FROM verification.results WHERE case_id = :id"),
        {"id": str(case.id)},
    ).fetchone()
    assert result_row is not None
    assert result_row[0] == "MANUAL_REVIEW"
    assert result_row[1] == "ManualReviewVerificationProvider"


# --- Full lifecycle: submit -> run_verification -> complete_manual_review
# -> write-back onto driver.documents/vehicle.documents.verification_status
# (Phase 2 / Task 2.6B). No HTTP endpoint composes these calls (none is
# documented — see ADR-0009, modules/verification/service.py's docstring)
# — this test is the composition, standing in for a future caller, same
# precedent as the vehicle-document tests above.


@pytest.mark.anyio
async def test_driver_document_full_lifecycle_reaches_approved(
    db: DbSession, service: VerificationService
) -> None:
    driver_id = _create_driver_id(db)
    document_service = DriverDocumentService(
        documents=SqlAlchemyDriverDocumentRepository(db)
    )
    document = document_service.submit_document(
        driver_id=driver_id,
        document_type="DRIVING_LICENSE",
        document_number="XY1234",
        evidence_uri="ref-1",
        expires_at=None,
    )
    db.commit()
    assert document.verification_status.value == "PENDING"

    case = service.submit_evidence(
        subject_type="DRIVER_DOCUMENT",
        subject_id=document.id,
        verification_type=VerificationType.DRIVER_DOCUMENT,
        evidence_uri="ref-1",
    )
    db.commit()

    case = await service.run_verification(case_id=case.id)
    db.commit()
    assert case.status.value == "MANUAL_REVIEW"
    # Document itself is untouched by run_verification()'s MANUAL_REVIEW
    # outcome — no document-level MANUAL_REVIEW status exists.
    unchanged = document_service.get_document(
        driver_id=driver_id, document_id=document.id
    )
    assert unchanged.verification_status.value == "PENDING"

    reviewer_id = uuid.uuid4()
    case = service.complete_manual_review(
        case_id=case.id,
        outcome=VerificationOutcome.APPROVED,
        reviewer_id=reviewer_id,
        reason=None,
    )
    db.commit()
    assert case.status.value == "APPROVED"

    approved_document = document_service.apply_verification_outcome(
        document_id=document.id, outcome=VerificationOutcome.APPROVED
    )
    db.commit()
    assert approved_document.verification_status.value == "APPROVED"

    row = db.execute(
        text("SELECT verification_status FROM driver.documents WHERE id = :id"),
        {"id": str(document.id)},
    ).fetchone()
    assert row is not None
    assert row[0] == "APPROVED"


@pytest.mark.anyio
async def test_vehicle_document_full_lifecycle_reaches_rejected(
    db: DbSession, service: VerificationService
) -> None:
    vehicle_id = _create_vehicle_id(db)
    document_service = VehicleDocumentService(
        documents=SqlAlchemyVehicleDocumentRepository(db)
    )
    document = document_service.submit_document(
        vehicle_id=vehicle_id,
        document_type="INSURANCE",
        document_number="POL-1",
        evidence_uri="ref-2",
        expires_at=None,
    )
    db.commit()

    case = service.submit_evidence(
        subject_type="VEHICLE_DOCUMENT",
        subject_id=document.id,
        verification_type=VerificationType.VEHICLE_DOCUMENT,
        evidence_uri="ref-2",
    )
    db.commit()
    case = await service.run_verification(case_id=case.id)
    db.commit()

    case = service.complete_manual_review(
        case_id=case.id,
        outcome=VerificationOutcome.REJECTED,
        reviewer_id=uuid.uuid4(),
        reason="Insurance expired at time of submission",
    )
    db.commit()
    assert case.status.value == "REJECTED"

    rejected_document = document_service.apply_verification_outcome(
        document_id=document.id, outcome=VerificationOutcome.REJECTED
    )
    db.commit()
    assert rejected_document.verification_status.value == "REJECTED"

    row = db.execute(
        text("SELECT verification_status FROM vehicle.documents WHERE id = :id"),
        {"id": str(document.id)},
    ).fetchone()
    assert row is not None
    assert row[0] == "REJECTED"

    # Two results exist for this case by now — run_verification()'s
    # MANUAL_REVIEW result (reason=None) and complete_manual_review()'s
    # terminal REJECTED result (with the reason) — fetch the latest.
    result_row = db.execute(
        text(
            "SELECT reason FROM verification.results WHERE case_id = :id "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"id": str(case.id)},
    ).fetchone()
    assert result_row is not None
    assert result_row[0] == "Insurance expired at time of submission"


def test_driver_document_ownership_isolation_for_apply_verification_outcome(
    db: DbSession,
) -> None:
    """Ownership isolation: applying an outcome to one driver's document
    id has no effect on another driver's documents."""
    driver_a = _create_driver_id(db)
    driver_b = _create_driver_id(db)
    document_service = DriverDocumentService(
        documents=SqlAlchemyDriverDocumentRepository(db)
    )
    doc_a = document_service.submit_document(
        driver_id=driver_a,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri="ref-a",
        expires_at=None,
    )
    doc_b = document_service.submit_document(
        driver_id=driver_b,
        document_type="DRIVING_LICENSE",
        document_number=None,
        evidence_uri="ref-b",
        expires_at=None,
    )
    db.commit()

    document_service.apply_verification_outcome(
        document_id=doc_a.id, outcome=VerificationOutcome.APPROVED
    )
    db.commit()

    untouched = document_service.get_document(driver_id=driver_b, document_id=doc_b.id)
    assert untouched.verification_status.value == "PENDING"
