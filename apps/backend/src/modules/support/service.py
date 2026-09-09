"""Application service (use cases) for Support.

Implements domain-design.md §21.3's CreateSupportCase/ResolveSupportCase
plus two additions ADR-0022 Decision 2 records: PostSupportMessage
("Support conversation") and AssignSupportCase (covers both "Support
assignment" and "Human escalation" — see that decision for why the two
roadmap tasks collapse into one command here). AskSupportAI is BLOCKED
(ADR-0022 Decision 4) — no method for it exists.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from modules.support.domain.entities import (
    CaseStatus,
    SenderType,
    SupportCase,
    SupportMessage,
)
from modules.support.domain.errors import (
    SupportCaseNotAssignableError,
    SupportCaseNotFoundError,
    SupportCaseNotResolvableError,
)
from modules.support.ports import SupportCaseRepository, SupportMessageRepository

_RESOLVED_OR_CLOSED = frozenset({CaseStatus.RESOLVED, CaseStatus.CLOSED})


class SupportService:
    def __init__(
        self, *, cases: SupportCaseRepository, messages: SupportMessageRepository
    ) -> None:
        self._cases = cases
        self._messages = messages

    def create_case(
        self,
        *,
        user_id: uuid.UUID,
        ride_id: uuid.UUID | None,
        category: str | None,
        sender_type: SenderType,
        message: str,
        now: datetime,
    ) -> tuple[SupportCase, SupportMessage]:
        """CreateSupportCase (domain-design.md §21.3). api-contracts.md
        §44's documented request body includes `message` alongside
        `category`/`ride_id` — that text becomes this case's first
        support.messages row, not a separate call the client must make
        (ADR-0022 Decision 1)."""
        case = self._cases.create(
            SupportCase.new(
                user_id=user_id, ride_id=ride_id, category=category, now=now
            )
        )
        first_message = self._messages.create(
            SupportMessage.new(
                case_id=case.id,
                sender_type=sender_type,
                sender_id=user_id,
                message=message,
                now=now,
            )
        )
        return case, first_message

    def post_message(
        self,
        *,
        case_id: uuid.UUID,
        sender_type: SenderType,
        sender_id: uuid.UUID | None,
        message: str,
        now: datetime,
    ) -> SupportMessage:
        """PostSupportMessage (ADR-0022 Decision 2) — "Support
        conversation". A pure append; does not itself change
        support.cases.status (no source document ties message-posting to
        a specific status transition)."""
        if self._cases.get_by_id(case_id) is None:
            raise SupportCaseNotFoundError("Support case not found.")
        return self._messages.create(
            SupportMessage.new(
                case_id=case_id,
                sender_type=sender_type,
                sender_id=sender_id,
                message=message,
                now=now,
            )
        )

    def assign_case(
        self, *, case_id: uuid.UUID, admin_id: uuid.UUID, now: datetime
    ) -> SupportCase:
        """AssignSupportCase (ADR-0022 Decision 2) — covers "Support
        assignment" and "Human escalation": OPEN -> ASSIGNED, sets
        assigned_admin_id. Concurrency: row-locked, same mechanism as
        DriverService.go_online()."""
        case = self._get_for_update(case_id)
        if case.status is not CaseStatus.OPEN:
            raise SupportCaseNotAssignableError(
                "This case is not in an assignable state."
            )
        case.status = CaseStatus.ASSIGNED
        case.assigned_admin_id = admin_id
        self._cases.save(case)
        return case

    def resolve_case(self, *, case_id: uuid.UUID, now: datetime) -> SupportCase:
        """ResolveSupportCase (domain-design.md §21.3). Valid from any
        status except already RESOLVED/CLOSED — a case may be resolved
        without ever having been formally assigned (e.g. a trivial
        question answered immediately)."""
        case = self._get_for_update(case_id)
        if case.status in _RESOLVED_OR_CLOSED:
            raise SupportCaseNotResolvableError("This case has already been resolved.")
        case.status = CaseStatus.RESOLVED
        self._cases.save(case)
        return case

    def get_case_with_messages(
        self, *, case_id: uuid.UUID
    ) -> tuple[SupportCase, list[SupportMessage]]:
        case = self._cases.get_by_id(case_id)
        if case is None:
            raise SupportCaseNotFoundError("Support case not found.")
        return case, self._messages.list_by_case(case_id)

    def search_cases(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[SupportCase], int]:
        return self._cases.search(status=status, offset=offset, limit=limit)

    def list_cases_for_user(
        self, *, user_id: uuid.UUID, status: str | None, offset: int, limit: int
    ) -> tuple[list[SupportCase], int]:
        """Self-service `GET /api/v1/support/cases` — the caller's own
        cases only (api-contracts.md §44, 2026-09-04)."""
        return self._cases.list_for_user(
            user_id=user_id, status=status, offset=offset, limit=limit
        )

    def count_unresolved_cases(self) -> int:
        return self._cases.count_unresolved()

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def count_cases_by_status(self) -> dict[str, int]:
        return self._cases.count_by_status()

    def average_case_resolution_minutes_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        return self._cases.average_resolution_minutes_in_range(since=since, until=until)

    def _get_for_update(self, case_id: uuid.UUID) -> SupportCase:
        case = self._cases.get_by_id_for_update(case_id)
        if case is None:
            raise SupportCaseNotFoundError("Support case not found.")
        return case
