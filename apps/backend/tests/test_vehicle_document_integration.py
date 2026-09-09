"""Integration tests: real Postgres session, exercising
VehicleDocumentService + SqlAlchemyVehicleDocumentRepository end-to-end.

No HTTP route exists for vehicle documents (see
docs/14-decisions/ADR-0007-document-type-and-endpoint-scope.md), so this
test drives the service/repository layer directly against a real
database session — the same infrastructure tests/test_vehicle_api.py
uses, minus the HTTP layer. A real identity.accounts + driver.drivers +
vehicle.vehicles row chain is created first to satisfy the documented
foreign keys (database-design.md §5, §7.1, §8.1, §8.2).

Skips (not fails) when Postgres is genuinely unreachable.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Generator

import pytest
from _integration_db import truncate_integration_tables
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession

from core.database import SessionLocal, engine
from modules.driver.models import DriverORM
from modules.identity.models import AccountORM
from modules.vehicle.domain.errors import VehicleDocumentNotFoundError
from modules.vehicle.models import VehicleORM
from modules.vehicle.repositories import SqlAlchemyVehicleDocumentRepository
from modules.vehicle.service import VehicleDocumentService


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
    writes to before every test, so tests run against the dedicated test
    database (see tests/conftest.py) never accumulate rows across runs —
    the root cause of the previously reported flaky registration_number
    collision. Local to this file only; not applied suite-wide."""
    truncate_integration_tables(engine)


@pytest.fixture
def db() -> Generator[DbSession, None, None]:
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


def _random_phone() -> str:
    return "+91" + "".join(str(secrets.randbelow(10)) for _ in range(10))


def _create_vehicle(db: DbSession) -> uuid.UUID:
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
        # range — see _clean_integration_tables above for why the old
        # narrow range was able to collide at all despite this.
        registration_number="BR01AB" + uuid.uuid4().hex[:16].upper(),
    )
    db.add(vehicle)
    db.flush()
    db.commit()
    return vehicle.id


@pytest.fixture
def service(db: DbSession) -> VehicleDocumentService:
    return VehicleDocumentService(documents=SqlAlchemyVehicleDocumentRepository(db))


def test_submit_document_persists_and_defaults_to_pending(
    db: DbSession, service: VehicleDocumentService
) -> None:
    vehicle_id = _create_vehicle(db)

    document = service.submit_document(
        vehicle_id=vehicle_id,
        document_type="insurance",
        document_number="POL-1",
        evidence_uri="ref-1",
        expires_at=None,
    )

    assert document.document_type == "INSURANCE"
    assert document.verification_status.value == "PENDING"

    row = db.execute(
        text("SELECT document_type FROM vehicle.documents WHERE id = :id"),
        {"id": str(document.id)},
    ).fetchone()
    assert row is not None
    assert row[0] == "INSURANCE"


def test_list_documents_scoped_to_one_vehicle(
    db: DbSession, service: VehicleDocumentService
) -> None:
    vehicle_id = _create_vehicle(db)
    other_vehicle_id = _create_vehicle(db)
    service.submit_document(
        vehicle_id=vehicle_id,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )
    service.submit_document(
        vehicle_id=other_vehicle_id,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )

    result = service.list_documents(vehicle_id=vehicle_id)

    assert len(result) == 1
    assert result[0].vehicle_id == vehicle_id


def test_get_document_denies_another_vehicles_document(
    db: DbSession, service: VehicleDocumentService
) -> None:
    vehicle_id = _create_vehicle(db)
    other_vehicle_id = _create_vehicle(db)
    document = service.submit_document(
        vehicle_id=vehicle_id,
        document_type="INSURANCE",
        document_number=None,
        evidence_uri=None,
        expires_at=None,
    )

    with pytest.raises(VehicleDocumentNotFoundError):
        service.get_document(vehicle_id=other_vehicle_id, document_id=document.id)


def test_vehicle_document_has_no_updated_at_column(db: DbSession) -> None:
    """Confirms the documented asymmetry vs. driver.documents (database-
    design.md §8.2 has no updated_at for vehicle.documents)."""
    columns = (
        db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'vehicle' AND table_name = 'documents'"
            )
        )
        .scalars()
        .all()
    )
    assert "updated_at" not in columns
    assert "created_at" in columns
