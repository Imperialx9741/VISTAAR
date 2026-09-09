"""Abstract interfaces (ports) the application layer depends on.

Concrete implementations live in repositories.py. Mirrors
modules/customer/ports.py's role for that module.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from modules.driver.domain.entities import Driver, DriverDocument


class DriverRepository(Protocol):
    def get_by_id(self, driver_id: uuid.UUID) -> Driver | None: ...

    def get_by_id_for_update(self, driver_id: uuid.UUID) -> Driver | None:
        """Same as get_by_id, but locks the row (SELECT ... FOR UPDATE)
        for the remainder of the current transaction. Used by
        go_online()/go_offline() (Phase 2 / Task 2.7B) to serialize
        concurrent operational_status transitions for the same driver —
        same reasoning as VehicleRepository.list_by_driver_for_update()
        (database-design.md §8.1.1, BR-122)."""
        ...

    def create(self, driver: Driver) -> Driver: ...

    def save(self, driver: Driver) -> None: ...

    def search(
        self,
        *,
        query: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Driver], int]:
        """Admin Web §4.2's "Search/list drivers". `query` matches
        `full_name` (ILIKE); `status` matches `verification_status`
        exactly (the same field Driver Review's own detail screen
        already surfaces, and the natural filter for a review queue —
        `operational_status` is a separate, unfiltered concern here)."""
        ...

    def count_total(self) -> int:
        """Admin Web §4.16 Drivers report (ADR-0047)."""
        ...

    def count_by_verification_status(self) -> dict[str, int]: ...

    def count_by_operational_status(self) -> dict[str, int]: ...

    def count_created_in_range(self, *, since: datetime, until: datetime) -> int: ...

    def list_all_ids(self) -> list[uuid.UUID]:
        """Every driver_id, unpaginated — Notification Broadcast's
        "All drivers" audience (ADR-0055). Same bare-id-list reasoning
        as CustomerRepository.list_all_ids()."""
        ...


class DriverDocumentRepository(Protocol):
    def create(self, document: DriverDocument) -> DriverDocument: ...

    def get_by_id(self, document_id: uuid.UUID) -> DriverDocument | None: ...

    def list_by_driver(self, driver_id: uuid.UUID) -> list[DriverDocument]: ...

    def save(self, document: DriverDocument) -> None: ...
