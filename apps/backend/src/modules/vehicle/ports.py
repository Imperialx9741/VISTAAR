"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from typing import Protocol

from modules.vehicle.domain.entities import Vehicle, VehicleDocument


class VehicleRepository(Protocol):
    def list_by_driver(self, driver_id: uuid.UUID) -> list[Vehicle]: ...

    def list_by_driver_for_update(self, driver_id: uuid.UUID) -> list[Vehicle]:
        """Same as list_by_driver, but locks every returned row
        (SELECT ... FOR UPDATE) for the remainder of the current
        transaction. Used by activate_vehicle() to serialize concurrent
        activation requests for the same driver — see
        docs/04-database/database-design.md §8.1.1 (Vehicle Activation
        Transaction) and business-rules.md BR-122."""
        ...

    def get_by_id(self, vehicle_id: uuid.UUID) -> Vehicle | None: ...

    def registration_number_exists(self, registration_number: str) -> bool: ...

    def create(self, vehicle: Vehicle) -> Vehicle: ...

    def save(self, vehicle: Vehicle) -> None: ...

    def search(
        self,
        *,
        query: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Vehicle], int]:
        """Admin Web §4.3's "Search/list vehicles". `query` matches
        `registration_number` (ILIKE) — the field an admin would
        actually have on hand searching for one vehicle, unlike
        `make`/`model` which only narrow a list. `status` matches
        `verification_status`."""
        ...


class VehicleDocumentRepository(Protocol):
    def create(self, document: VehicleDocument) -> VehicleDocument: ...

    def get_by_id(self, document_id: uuid.UUID) -> VehicleDocument | None: ...

    def list_by_vehicle(self, vehicle_id: uuid.UUID) -> list[VehicleDocument]: ...

    def save(self, document: VehicleDocument) -> None: ...
