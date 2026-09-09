"""SQLAlchemy-backed implementation of CustomerRepository.

Translates between the ORM rows (models.py) and the pure domain entity
(domain/entities.py) — mirrors modules/identity/repositories.py's role.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from modules.customer.domain.entities import Customer, CustomerStatus
from modules.customer.models import CustomerORM, CustomerPreferencesORM


def _customer_from_orm(
    customer_row: CustomerORM, preferences_row: CustomerPreferencesORM
) -> Customer:
    return Customer(
        id=customer_row.id,
        full_name=customer_row.full_name,
        profile_photo_uri=customer_row.profile_photo_uri,
        status=CustomerStatus(customer_row.status),
        language=preferences_row.language,
        notification_enabled=preferences_row.notification_enabled,
        created_at=customer_row.created_at,
        updated_at=customer_row.updated_at,
    )


class SqlAlchemyCustomerRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get_by_id(self, customer_id: uuid.UUID) -> Customer | None:
        customer_row = self._db.get(CustomerORM, customer_id)
        if customer_row is None:
            return None
        preferences_row = self._db.get(CustomerPreferencesORM, customer_id)
        if preferences_row is None:
            # Should not happen — create() always inserts both rows
            # together — but fail loudly rather than returning a
            # half-built domain entity if it ever does.
            raise LookupError(
                f"customer.preferences row missing for customer {customer_id}"
            )
        return _customer_from_orm(customer_row, preferences_row)

    def create(self, customer: Customer) -> Customer:
        customer_row = CustomerORM(
            id=customer.id,
            full_name=customer.full_name,
            profile_photo_uri=customer.profile_photo_uri,
            status=customer.status.value,
        )
        preferences_row = CustomerPreferencesORM(
            customer_id=customer.id,
            language=customer.language,
            notification_enabled=customer.notification_enabled,
        )
        self._db.add(customer_row)
        self._db.add(preferences_row)
        self._db.flush()
        self._db.refresh(customer_row)
        self._db.refresh(preferences_row)
        return _customer_from_orm(customer_row, preferences_row)

    def save(self, customer: Customer) -> None:
        customer_row = self._db.get(CustomerORM, customer.id)
        preferences_row = self._db.get(CustomerPreferencesORM, customer.id)
        if customer_row is None or preferences_row is None:
            raise LookupError(f"Customer {customer.id} not found")

        customer_row.full_name = customer.full_name
        customer_row.profile_photo_uri = customer.profile_photo_uri
        customer_row.status = customer.status.value
        preferences_row.language = customer.language
        preferences_row.notification_enabled = customer.notification_enabled
        self._db.flush()
        self._db.refresh(customer_row)

        # customer_row.updated_at is server-computed (onupdate=func.now()
        # in models.py) and only known accurately after the flush+refresh
        # above — write it back onto the passed-in domain object so
        # callers (service.py returns `customer` directly after calling
        # save()) report the value that was actually persisted, not the
        # Python-side datetime.now(UTC) service.py set before saving.
        customer.updated_at = customer_row.updated_at

    def search(
        self, *, query: str | None, offset: int, limit: int
    ) -> tuple[list[Customer], int]:
        base = select(CustomerORM, CustomerPreferencesORM).join(
            CustomerPreferencesORM,
            CustomerPreferencesORM.customer_id == CustomerORM.id,
        )
        if query:
            base = base.where(CustomerORM.full_name.ilike(f"%{query}%"))

        total = self._db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()
        rows = self._db.execute(
            base.order_by(CustomerORM.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return [
            _customer_from_orm(customer_row, preferences_row)
            for customer_row, preferences_row in rows
        ], total

    def count_total(self) -> int:
        return self._db.execute(
            select(func.count()).select_from(CustomerORM)
        ).scalar_one()

    def count_created_in_range(self, *, since: datetime, until: datetime) -> int:
        return self._db.execute(
            select(func.count())
            .select_from(CustomerORM)
            .where(CustomerORM.created_at >= since)
            .where(CustomerORM.created_at < until)
        ).scalar_one()

    def list_all_ids(self) -> list[uuid.UUID]:
        return list(self._db.execute(select(CustomerORM.id)).scalars().all())
