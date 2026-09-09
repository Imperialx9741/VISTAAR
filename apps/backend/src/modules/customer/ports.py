"""Abstract interface (port) the application layer depends on.

Concrete implementation lives in repositories.py. Mirrors
modules/identity/ports.py's role for that module.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from modules.customer.domain.entities import Customer


class CustomerRepository(Protocol):
    def get_by_id(self, customer_id: uuid.UUID) -> Customer | None: ...

    def create(self, customer: Customer) -> Customer: ...

    def save(self, customer: Customer) -> None: ...

    def search(
        self, *, query: str | None, offset: int, limit: int
    ) -> tuple[list[Customer], int]:
        """Admin Web §4.1's "Search/list customers". `query` matches
        `full_name` only (ILIKE) — the only customer-identifying field
        this module's own schema holds; phone lives in
        identity.accounts, a separate module this repository does not
        reach into (same boundary Driver Review's own account+driver
        composition already keeps at the router layer, not inside a
        repository query)."""
        ...

    def count_total(self) -> int:
        """Admin Web §4.16 Customers report (ADR-0047)."""
        ...

    def count_created_in_range(self, *, since: datetime, until: datetime) -> int: ...

    def list_all_ids(self) -> list[uuid.UUID]:
        """Every customer_id, unpaginated — Notification Broadcast's
        "All customers" audience (ADR-0055). Deliberately a bare id
        list, not search()'s own full-entity/preferences-joined shape:
        a broadcast fan-out has no use for the extra columns and this
        can run against the entire table."""
        ...
