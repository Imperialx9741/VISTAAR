"""Abstract interfaces (ports) the application layer depends on."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from modules.support.domain.entities import SupportCase, SupportMessage


class SupportCaseRepository(Protocol):
    def create(self, case: SupportCase) -> SupportCase: ...

    def get_by_id(self, case_id: uuid.UUID) -> SupportCase | None: ...

    def get_by_id_for_update(self, case_id: uuid.UUID) -> SupportCase | None:
        """Locks the row (SELECT ... FOR UPDATE) for the remainder of
        the current transaction — used by assign/resolve to serialize
        concurrent transitions on the same case, same mechanism as
        modules.driver.service.DriverService.go_online()."""
        ...

    def save(self, case: SupportCase) -> None: ...

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[SupportCase], int]:
        """Admin Web §4.14's "Search/list all support cases". Newest
        first."""
        ...

    def list_for_user(
        self, *, user_id: uuid.UUID, status: str | None, offset: int, limit: int
    ) -> tuple[list[SupportCase], int]:
        """Self-service `GET /api/v1/support/cases` (api-contracts.md
        §44, added 2026-09-04 — the "missing support-case list
        endpoint"). Unlike search() above, always scoped to a single
        caller's own cases — never exposes another user's support
        history. Newest first, same ordering as search()."""
        ...

    def count_unresolved(self) -> int:
        """Admin Web §3's Dashboard "Open support cases" widget — every
        status except RESOLVED/CLOSED."""
        ...

    def count_by_status(self) -> dict[str, int]:
        """Admin Web §4.16 Safety/Support report (ADR-0047)."""
        ...

    def average_resolution_minutes_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        """AVG(updated_at - created_at) in minutes, for RESOLVED cases
        with `updated_at` in [since, until) — SupportCase has no
        dedicated `resolved_at` column, unlike SafetyIncident, so
        `updated_at` is the closest available signal for "when this
        left RESOLVED status". 0 if none resolved in range."""
        ...


class SupportMessageRepository(Protocol):
    def create(self, message: SupportMessage) -> SupportMessage: ...

    def list_by_case(self, case_id: uuid.UUID) -> list[SupportMessage]: ...
