"""SQLAlchemy-backed implementation of RideRepository."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from modules.ride.domain.entities import (
    ChangeRequest,
    ChangeRequestCustomerDecision,
    ChangeRequestDriverDecision,
    ChangeRequestStatus,
    ChangeRequestType,
    Coordinates,
    EarlyDropRequest,
    GpsDispute,
    GpsDisputeDecision,
    GpsDisputeEvidence,
    GpsDisputeEvidenceType,
    GpsDisputeStatus,
    GpsVerification,
    GpsVerificationResult,
    GpsVerificationType,
    Ride,
    RideOtp,
    RideOtpStatus,
    RideStatus,
)
from modules.ride.models import (
    ChangeRequestORM,
    EarlyDropRequestORM,
    GpsDisputeEvidenceORM,
    GpsDisputeORM,
    GpsVerificationORM,
    RideORM,
    RideOtpORM,
    RideStateHistoryORM,
)
from modules.vehicle.domain.entities import CabTier, VehicleCategory

_POINT_WKT_RE = re.compile(r"^POINT\(([-0-9.]+) ([-0-9.]+)\)$")


def _to_wkt(coordinates: Coordinates) -> str:
    # WKT/PostGIS point order is X Y, i.e. longitude then latitude.
    return f"POINT({coordinates.longitude} {coordinates.latitude})"


def _from_wkt(wkt: str) -> Coordinates:
    match = _POINT_WKT_RE.match(wkt)
    if not match:
        raise ValueError(f"Unexpected geometry WKT value: {wkt!r}")
    longitude, latitude = float(match.group(1)), float(match.group(2))
    return Coordinates(latitude=latitude, longitude=longitude)


def _ride_from_orm(row: RideORM) -> Ride:
    return Ride(
        id=row.id,
        customer_id=row.customer_id,
        driver_id=row.driver_id,
        vehicle_id=row.vehicle_id,
        status=RideStatus(row.status),
        requested_vehicle_category=VehicleCategory(row.requested_vehicle_category),
        requested_cab_tier=(
            CabTier(row.requested_cab_tier)
            if row.requested_cab_tier is not None
            else None
        ),
        original_pickup=_from_wkt(row.original_pickup),
        current_pickup=_from_wkt(row.current_pickup),
        original_destination=_from_wkt(row.original_destination),
        current_destination=_from_wkt(row.current_destination),
        active_fare_quote_id=row.active_fare_quote_id,
        scheduled_for=row.scheduled_for,
        lock_in_at=row.lock_in_at,
        linked_contact_name=row.linked_contact_name,
        linked_contact_phone=row.linked_contact_phone,
        requested_at=row.requested_at,
        accepted_at=row.accepted_at,
        arrived_at=row.arrived_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        closed_at=row.closed_at,
        cancelled_at=row.cancelled_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyRideRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, ride: Ride) -> Ride:
        row = RideORM(
            id=ride.id,
            customer_id=ride.customer_id,
            driver_id=ride.driver_id,
            vehicle_id=ride.vehicle_id,
            status=ride.status.value,
            requested_vehicle_category=ride.requested_vehicle_category.value,
            requested_cab_tier=(
                ride.requested_cab_tier.value
                if ride.requested_cab_tier is not None
                else None
            ),
            original_pickup=_to_wkt(ride.original_pickup),
            current_pickup=_to_wkt(ride.current_pickup),
            original_destination=_to_wkt(ride.original_destination),
            current_destination=_to_wkt(ride.current_destination),
            active_fare_quote_id=ride.active_fare_quote_id,
            scheduled_for=ride.scheduled_for,
            lock_in_at=ride.lock_in_at,
            linked_contact_name=ride.linked_contact_name,
            linked_contact_phone=ride.linked_contact_phone,
        )
        self._db.add(row)
        self._db.flush()

        # database-design.md §9.2: "Every authoritative ride-state
        # transition must create a history record" (ADR-0010 Decision 3).
        # actor_type/actor_id record the customer who requested the ride
        # — both columns are free-form/nullable, not a new invented rule.
        history = RideStateHistoryORM(
            ride_id=row.id,
            from_status=None,
            to_status=ride.status.value,
            reason=None,
            actor_type="CUSTOMER",
            actor_id=ride.customer_id,
        )
        self._db.add(history)
        self._db.flush()

        self._db.refresh(row)
        return _ride_from_orm(row)

    def get_by_id(self, ride_id: uuid.UUID) -> Ride | None:
        row = self._db.get(RideORM, ride_id)
        return _ride_from_orm(row) if row else None

    def get_by_id_for_update(self, ride_id: uuid.UUID) -> Ride | None:
        row = self._db.execute(
            select(RideORM).where(RideORM.id == ride_id).with_for_update()
        ).scalar_one_or_none()
        return _ride_from_orm(row) if row else None

    def save(
        self,
        ride: Ride,
        *,
        from_status: RideStatus,
        reason: str | None,
        actor_type: str,
        actor_id: uuid.UUID,
    ) -> None:
        row = self._db.get(RideORM, ride.id)
        if row is None:
            raise LookupError(f"Ride {ride.id} not found")

        row.status = ride.status.value
        row.driver_id = ride.driver_id
        row.vehicle_id = ride.vehicle_id
        # ADR-0033 — current_pickup only ever differs from what's already
        # stored when this save() call is the pickup-change-PASS
        # rematch (the one status-transition path that also changes the
        # pickup); every other caller passes it back unchanged, so this
        # is a safe no-op write for them.
        row.current_pickup = _to_wkt(ride.current_pickup)
        row.current_destination = _to_wkt(ride.current_destination)
        row.accepted_at = ride.accepted_at
        row.arrived_at = ride.arrived_at
        row.started_at = ride.started_at
        row.completed_at = ride.completed_at
        row.closed_at = ride.closed_at
        row.cancelled_at = ride.cancelled_at
        self._db.flush()

        # database-design.md §9.2: "Every authoritative ride-state
        # transition must create a history record" — same requirement
        # create() already satisfies (ADR-0010 Decision 3).
        history = RideStateHistoryORM(
            ride_id=ride.id,
            from_status=from_status.value,
            to_status=ride.status.value,
            reason=reason,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        self._db.add(history)
        self._db.flush()

        self._db.refresh(row)
        ride.updated_at = row.updated_at

    def set_active_fare_quote(
        self, ride_id: uuid.UUID, fare_quote_id: uuid.UUID
    ) -> None:
        row = self._db.get(RideORM, ride_id)
        if row is None:
            raise LookupError(f"Ride {ride_id} not found")
        row.active_fare_quote_id = fare_quote_id
        self._db.flush()

    def update_current_pickup(self, ride_id: uuid.UUID, pickup: Coordinates) -> None:
        row = self._db.get(RideORM, ride_id)
        if row is None:
            raise LookupError(f"Ride {ride_id} not found")
        row.current_pickup = _to_wkt(pickup)
        self._db.flush()

    def update_current_destination(
        self, ride_id: uuid.UUID, destination: Coordinates
    ) -> None:
        row = self._db.get(RideORM, ride_id)
        if row is None:
            raise LookupError(f"Ride {ride_id} not found")
        row.current_destination = _to_wkt(destination)
        self._db.flush()

    def search(
        self,
        *,
        status: str | None,
        driver_id: uuid.UUID | None,
        customer_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Ride], int]:
        # Phase 16 (ADR-0023) — allow-listed filters only, matching
        # api-contracts.md §51's explicit "clients cannot inject
        # arbitrary SQL fields" requirement: every WHERE clause below
        # comes from a named parameter, never a client-supplied field
        # name.
        stmt = select(RideORM)
        count_stmt = select(func.count()).select_from(RideORM)
        if status is not None:
            stmt = stmt.where(RideORM.status == status)
            count_stmt = count_stmt.where(RideORM.status == status)
        if driver_id is not None:
            stmt = stmt.where(RideORM.driver_id == driver_id)
            count_stmt = count_stmt.where(RideORM.driver_id == driver_id)
        if customer_id is not None:
            stmt = stmt.where(RideORM.customer_id == customer_id)
            count_stmt = count_stmt.where(RideORM.customer_id == customer_id)

        total = self._db.execute(count_stmt).scalar_one()
        rows = (
            self._db.execute(
                stmt.order_by(RideORM.requested_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )
        return [_ride_from_orm(row) for row in rows], total

    def list_due_scheduled(self, *, before: datetime, limit: int) -> list[Ride]:
        rows = (
            self._db.execute(
                select(RideORM)
                .where(RideORM.status == RideStatus.SCHEDULED.value)
                .where(RideORM.lock_in_at <= before)
                .order_by(RideORM.lock_in_at.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_ride_from_orm(row) for row in rows]

    def count_by_status_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        rows = self._db.execute(
            select(RideORM.status, func.count())
            .where(RideORM.created_at >= since)
            .where(RideORM.created_at < until)
            .group_by(RideORM.status)
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def count_by_vehicle_category_in_range(
        self, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        rows = self._db.execute(
            select(RideORM.requested_vehicle_category, func.count())
            .where(RideORM.created_at >= since)
            .where(RideORM.created_at < until)
            .group_by(RideORM.requested_vehicle_category)
        ).all()
        return {key: value for key, value in rows}  # noqa: C416

    def list_active_fare_quote_ids_for_closed_in_range(
        self, *, since: datetime, until: datetime
    ) -> list[uuid.UUID]:
        ids = (
            self._db.execute(
                select(RideORM.active_fare_quote_id)
                .where(RideORM.status == RideStatus.CLOSED.value)
                .where(RideORM.created_at >= since)
                .where(RideORM.created_at < until)
                .where(RideORM.active_fare_quote_id.is_not(None))
            )
            .scalars()
            .all()
        )
        # The WHERE clause above already excludes NULLs at the SQL
        # level; this comprehension only narrows the type mypy sees
        # (Sequence[UUID | None], since the column itself is nullable)
        # to match the port's documented list[uuid.UUID] return shape.
        return [i for i in ids if i is not None]


def _otp_from_orm(row: RideOtpORM) -> RideOtp:
    return RideOtp(
        id=row.id,
        ride_id=row.ride_id,
        otp_hash=row.otp_hash,
        expires_at=row.expires_at,
        attempts=row.attempts,
        status=RideOtpStatus(row.status),
        created_at=row.created_at,
    )


class SqlAlchemyRideOtpRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, otp: RideOtp) -> RideOtp:
        row = RideOtpORM(
            id=otp.id,
            ride_id=otp.ride_id,
            otp_hash=otp.otp_hash,
            expires_at=otp.expires_at,
            attempts=otp.attempts,
            status=otp.status.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _otp_from_orm(row)

    def get_active_for_update(self, ride_id: uuid.UUID) -> RideOtp | None:
        row = (
            self._db.execute(
                select(RideOtpORM)
                .where(RideOtpORM.ride_id == ride_id)
                .where(RideOtpORM.status == RideOtpStatus.ACTIVE.value)
                .order_by(RideOtpORM.created_at.desc())
                .with_for_update()
            )
            .scalars()
            .first()
        )
        return _otp_from_orm(row) if row else None

    def save(self, otp: RideOtp) -> None:
        row = self._db.get(RideOtpORM, otp.id)
        if row is None:
            raise LookupError(f"RideOtp {otp.id} not found")
        row.attempts = otp.attempts
        row.status = otp.status.value
        self._db.flush()


def _gps_verification_from_orm(row: GpsVerificationORM) -> GpsVerification:
    return GpsVerification(
        id=row.id,
        ride_id=row.ride_id,
        verification_type=GpsVerificationType(row.verification_type),
        latitude=float(row.latitude),
        longitude=float(row.longitude),
        reference_latitude=(
            float(row.reference_latitude)
            if row.reference_latitude is not None
            else None
        ),
        reference_longitude=(
            float(row.reference_longitude)
            if row.reference_longitude is not None
            else None
        ),
        distance_meters=(
            float(row.distance_meters) if row.distance_meters is not None else None
        ),
        result=GpsVerificationResult(row.result),
        created_at=row.created_at,
    )


class SqlAlchemyGpsVerificationRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, verification: GpsVerification) -> GpsVerification:
        row = GpsVerificationORM(
            id=verification.id,
            ride_id=verification.ride_id,
            verification_type=verification.verification_type.value,
            latitude=verification.latitude,
            longitude=verification.longitude,
            reference_latitude=verification.reference_latitude,
            reference_longitude=verification.reference_longitude,
            distance_meters=verification.distance_meters,
            result=verification.result.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _gps_verification_from_orm(row)

    def count_failed(self, ride_id: uuid.UUID, *, verification_type: str) -> int:
        return self._db.execute(
            select(func.count())
            .select_from(GpsVerificationORM)
            .where(GpsVerificationORM.ride_id == ride_id)
            .where(GpsVerificationORM.verification_type == verification_type)
            .where(GpsVerificationORM.result == GpsVerificationResult.FAIL.value)
        ).scalar_one()


def _early_drop_request_from_orm(row: EarlyDropRequestORM) -> EarlyDropRequest:
    return EarlyDropRequest(
        id=row.id,
        ride_id=row.ride_id,
        requested_by=row.requested_by,
        reason=row.reason,
        customer_confirmed=row.customer_confirmed,
        driver_confirmed=row.driver_confirmed,
        gps_location=_from_wkt(row.gps_location) if row.gps_location else None,
        requested_at=row.requested_at,
        confirmed_at=row.confirmed_at,
    )


class SqlAlchemyEarlyDropRequestRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, request: EarlyDropRequest) -> EarlyDropRequest:
        row = EarlyDropRequestORM(
            id=request.id,
            ride_id=request.ride_id,
            requested_by=request.requested_by,
            reason=request.reason,
            customer_confirmed=request.customer_confirmed,
            driver_confirmed=request.driver_confirmed,
            gps_location=(
                _to_wkt(request.gps_location) if request.gps_location else None
            ),
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _early_drop_request_from_orm(row)

    def get_pending_for_update(self, ride_id: uuid.UUID) -> EarlyDropRequest | None:
        row = (
            self._db.execute(
                select(EarlyDropRequestORM)
                .where(EarlyDropRequestORM.ride_id == ride_id)
                .where(EarlyDropRequestORM.confirmed_at.is_(None))
                .order_by(EarlyDropRequestORM.requested_at.desc())
                .with_for_update()
            )
            .scalars()
            .first()
        )
        return _early_drop_request_from_orm(row) if row else None

    def save(self, request: EarlyDropRequest) -> None:
        row = self._db.get(EarlyDropRequestORM, request.id)
        if row is None:
            raise LookupError(f"EarlyDropRequest {request.id} not found")
        row.customer_confirmed = request.customer_confirmed
        row.driver_confirmed = request.driver_confirmed
        row.gps_location = (
            _to_wkt(request.gps_location) if request.gps_location else None
        )
        row.confirmed_at = request.confirmed_at
        self._db.flush()

    def delete(self, request_id: uuid.UUID) -> None:
        row = self._db.get(EarlyDropRequestORM, request_id)
        if row is None:
            raise LookupError(f"EarlyDropRequest {request_id} not found")
        self._db.delete(row)
        self._db.flush()


def _change_request_from_orm(row: ChangeRequestORM) -> ChangeRequest:
    assert (
        row.new_location is not None
    )  # always set for PICKUP_CHANGE/DESTINATION_CHANGE
    return ChangeRequest(
        id=row.id,
        ride_id=row.ride_id,
        request_type=ChangeRequestType(row.request_type),
        requested_by=row.requested_by,
        old_location=_from_wkt(row.old_location) if row.old_location else None,
        new_location=_from_wkt(row.new_location),
        old_fare_quote_id=row.old_fare_quote_id,
        new_fare_quote_id=row.new_fare_quote_id,
        status=ChangeRequestStatus(row.status),
        driver_decision=(
            ChangeRequestDriverDecision(row.driver_decision)
            if row.driver_decision
            else None
        ),
        customer_decision=(
            ChangeRequestCustomerDecision(row.customer_decision)
            if row.customer_decision
            else None
        ),
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


class SqlAlchemyChangeRequestRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, request: ChangeRequest) -> ChangeRequest:
        row = ChangeRequestORM(
            id=request.id,
            ride_id=request.ride_id,
            request_type=request.request_type.value,
            requested_by=request.requested_by,
            old_location=(
                _to_wkt(request.old_location) if request.old_location else None
            ),
            new_location=_to_wkt(request.new_location),
            old_fare_quote_id=request.old_fare_quote_id,
            new_fare_quote_id=request.new_fare_quote_id,
            status=request.status.value,
            driver_decision=(
                request.driver_decision.value if request.driver_decision else None
            ),
            customer_decision=(
                request.customer_decision.value if request.customer_decision else None
            ),
            created_at=request.created_at,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _change_request_from_orm(row)

    def get_pending_for_update(
        self, ride_id: uuid.UUID, *, request_type: ChangeRequestType
    ) -> ChangeRequest | None:
        row = (
            self._db.execute(
                select(ChangeRequestORM)
                .where(ChangeRequestORM.ride_id == ride_id)
                .where(ChangeRequestORM.request_type == request_type.value)
                .where(
                    ChangeRequestORM.status.in_(
                        (
                            ChangeRequestStatus.AWAITING_DRIVER_DECISION.value,
                            ChangeRequestStatus.AWAITING_CUSTOMER_CONFIRMATION.value,
                        )
                    )
                )
                .order_by(ChangeRequestORM.created_at.desc())
                .with_for_update()
            )
            .scalars()
            .first()
        )
        return _change_request_from_orm(row) if row else None

    def save(self, request: ChangeRequest) -> None:
        row = self._db.get(ChangeRequestORM, request.id)
        if row is None:
            raise LookupError(f"ChangeRequest {request.id} not found")
        row.status = request.status.value
        row.driver_decision = (
            request.driver_decision.value if request.driver_decision else None
        )
        row.customer_decision = (
            request.customer_decision.value if request.customer_decision else None
        )
        row.new_fare_quote_id = request.new_fare_quote_id
        row.resolved_at = request.resolved_at
        self._db.flush()


def _gps_dispute_from_orm(row: GpsDisputeORM) -> GpsDispute:
    return GpsDispute(
        id=row.id,
        ride_id=row.ride_id,
        gps_verification_id=row.gps_verification_id,
        verification_type=GpsVerificationType(row.verification_type),
        opened_at=row.opened_at,
        evidence_deadline=row.evidence_deadline,
        status=GpsDisputeStatus(row.status),
        decision=GpsDisputeDecision(row.decision) if row.decision else None,
        decided_by=row.decided_by,
        decided_reason=row.decided_reason,
        decided_at=row.decided_at,
    )


class SqlAlchemyGpsDisputeRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, dispute: GpsDispute) -> GpsDispute:
        row = GpsDisputeORM(
            id=dispute.id,
            ride_id=dispute.ride_id,
            gps_verification_id=dispute.gps_verification_id,
            verification_type=dispute.verification_type.value,
            opened_at=dispute.opened_at,
            evidence_deadline=dispute.evidence_deadline,
            status=dispute.status.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _gps_dispute_from_orm(row)

    def get_by_id_for_update(self, dispute_id: uuid.UUID) -> GpsDispute | None:
        row = self._db.execute(
            select(GpsDisputeORM)
            .where(GpsDisputeORM.id == dispute_id)
            .with_for_update()
        ).scalar_one_or_none()
        return _gps_dispute_from_orm(row) if row else None

    def get_by_id(self, dispute_id: uuid.UUID) -> GpsDispute | None:
        row = self._db.get(GpsDisputeORM, dispute_id)
        return _gps_dispute_from_orm(row) if row else None

    def list_for_ride(self, ride_id: uuid.UUID) -> list[GpsDispute]:
        rows = (
            self._db.execute(
                select(GpsDisputeORM)
                .where(GpsDisputeORM.ride_id == ride_id)
                .order_by(GpsDisputeORM.opened_at.desc())
            )
            .scalars()
            .all()
        )
        return [_gps_dispute_from_orm(row) for row in rows]

    def save(self, dispute: GpsDispute) -> None:
        row = self._db.get(GpsDisputeORM, dispute.id)
        if row is None:
            raise LookupError(f"GpsDispute {dispute.id} not found")
        row.status = dispute.status.value
        row.decision = dispute.decision.value if dispute.decision else None
        row.decided_by = dispute.decided_by
        row.decided_reason = dispute.decided_reason
        row.decided_at = dispute.decided_at
        self._db.flush()

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[GpsDispute], int]:
        stmt = select(GpsDisputeORM)
        count_stmt = select(func.count()).select_from(GpsDisputeORM)
        if status is not None:
            stmt = stmt.where(GpsDisputeORM.status == status)
            count_stmt = count_stmt.where(GpsDisputeORM.status == status)

        total = self._db.execute(count_stmt).scalar_one()
        rows = (
            self._db.execute(
                stmt.order_by(GpsDisputeORM.opened_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_gps_dispute_from_orm(row) for row in rows], total


def _gps_dispute_evidence_from_orm(row: GpsDisputeEvidenceORM) -> GpsDisputeEvidence:
    return GpsDisputeEvidence(
        id=row.id,
        dispute_id=row.dispute_id,
        submitted_by=row.submitted_by,
        evidence_type=GpsDisputeEvidenceType(row.evidence_type),
        uri=row.uri,
        text_explanation=row.text_explanation,
        submitted_at=row.submitted_at,
    )


class SqlAlchemyGpsDisputeEvidenceRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, evidence: GpsDisputeEvidence) -> GpsDisputeEvidence:
        row = GpsDisputeEvidenceORM(
            id=evidence.id,
            dispute_id=evidence.dispute_id,
            submitted_by=evidence.submitted_by,
            evidence_type=evidence.evidence_type.value,
            uri=evidence.uri,
            text_explanation=evidence.text_explanation,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _gps_dispute_evidence_from_orm(row)

    def list_for_dispute(self, dispute_id: uuid.UUID) -> list[GpsDisputeEvidence]:
        rows = (
            self._db.execute(
                select(GpsDisputeEvidenceORM)
                .where(GpsDisputeEvidenceORM.dispute_id == dispute_id)
                .order_by(GpsDisputeEvidenceORM.submitted_at.asc())
            )
            .scalars()
            .all()
        )
        return [_gps_dispute_evidence_from_orm(row) for row in rows]
