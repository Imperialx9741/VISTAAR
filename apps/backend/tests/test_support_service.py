"""Unit tests for SupportService against in-memory fake repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from modules.support.domain.entities import (
    CaseStatus,
    SenderType,
    SupportCase,
    SupportMessage,
)
from modules.support.domain.errors import (
    InvalidMessageError,
    SupportCaseNotAssignableError,
    SupportCaseNotFoundError,
    SupportCaseNotResolvableError,
)
from modules.support.service import SupportService

USER_ID = uuid.uuid4()
RIDE_ID = uuid.uuid4()
ADMIN_ID = uuid.uuid4()
NOW = datetime.now(UTC)


class FakeSupportCaseRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, SupportCase] = {}

    def create(self, case: SupportCase) -> SupportCase:
        self.by_id[case.id] = case
        return case

    def get_by_id(self, case_id: uuid.UUID) -> SupportCase | None:
        return self.by_id.get(case_id)

    def get_by_id_for_update(self, case_id: uuid.UUID) -> SupportCase | None:
        return self.by_id.get(case_id)

    def save(self, case: SupportCase) -> None:
        self.by_id[case.id] = case

    def search(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[SupportCase], int]:
        matches = sorted(
            (
                c
                for c in self.by_id.values()
                if status is None or c.status.value == status
            ),
            key=lambda c: c.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)

    def list_for_user(
        self, *, user_id: uuid.UUID, status: str | None, offset: int, limit: int
    ) -> tuple[list[SupportCase], int]:
        matches = sorted(
            (
                c
                for c in self.by_id.values()
                if c.user_id == user_id
                and (status is None or c.status.value == status)
            ),
            key=lambda c: c.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)

    def count_unresolved(self) -> int:
        return sum(
            1
            for c in self.by_id.values()
            if c.status.value not in ("RESOLVED", "CLOSED")
        )

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in self.by_id.values():
            counts[c.status.value] = counts.get(c.status.value, 0) + 1
        return counts

    def average_resolution_minutes_in_range(
        self, *, since: datetime, until: datetime
    ) -> Decimal:
        durations = [
            (c.updated_at - c.created_at).total_seconds() / 60
            for c in self.by_id.values()
            if c.status.value == "RESOLVED" and since <= c.updated_at < until
        ]
        if not durations:
            return Decimal("0")
        return Decimal(str(sum(durations) / len(durations)))


class FakeSupportMessageRepository:
    def __init__(self) -> None:
        self.created: list[SupportMessage] = []

    def create(self, message: SupportMessage) -> SupportMessage:
        self.created.append(message)
        return message

    def list_by_case(self, case_id: uuid.UUID) -> list[SupportMessage]:
        return [m for m in self.created if m.case_id == case_id]


@pytest.fixture
def cases() -> FakeSupportCaseRepository:
    return FakeSupportCaseRepository()


@pytest.fixture
def messages() -> FakeSupportMessageRepository:
    return FakeSupportMessageRepository()


@pytest.fixture
def service(
    cases: FakeSupportCaseRepository, messages: FakeSupportMessageRepository
) -> SupportService:
    return SupportService(cases=cases, messages=messages)


def _create_case(service: SupportService, **overrides: object) -> SupportCase:
    defaults: dict[str, object] = {
        "user_id": USER_ID,
        "ride_id": RIDE_ID,
        "category": "PAYMENT",
        "sender_type": SenderType.CUSTOMER,
        "message": "Why was I charged ₹30?",
        "now": NOW,
    }
    defaults.update(overrides)
    case, _first_message = service.create_case(**defaults)
    return case


def test_create_case_starts_open(service: SupportService) -> None:
    case = _create_case(service)

    assert case.status is CaseStatus.OPEN
    assert case.user_id == USER_ID
    assert case.ride_id == RIDE_ID
    assert case.category == "PAYMENT"
    assert case.priority == "NORMAL"
    assert case.assigned_admin_id is None


def test_create_case_writes_the_first_message(
    service: SupportService, messages: FakeSupportMessageRepository
) -> None:
    case = _create_case(service, message="Why was I charged ₹30?")

    thread = messages.list_by_case(case.id)
    assert len(thread) == 1
    assert thread[0].message == "Why was I charged ₹30?"
    assert thread[0].sender_type is SenderType.CUSTOMER
    assert thread[0].sender_id == USER_ID


def test_create_case_normalizes_category(service: SupportService) -> None:
    case = _create_case(service, category="  payment  ")
    assert case.category == "PAYMENT"


def test_create_case_allows_no_category_or_ride(service: SupportService) -> None:
    case = _create_case(service, category=None, ride_id=None)
    assert case.category is None
    assert case.ride_id is None


def test_create_case_rejects_blank_message(service: SupportService) -> None:
    with pytest.raises(InvalidMessageError):
        _create_case(service, message="   ")


def test_post_message_appends_without_changing_status(
    service: SupportService, messages: FakeSupportMessageRepository
) -> None:
    case = _create_case(service)

    service.post_message(
        case_id=case.id,
        sender_type=SenderType.ADMIN,
        sender_id=ADMIN_ID,
        message="Looking into this now.",
        now=NOW,
    )

    thread = messages.list_by_case(case.id)
    assert len(thread) == 2
    assert thread[1].sender_type is SenderType.ADMIN
    assert thread[1].sender_id == ADMIN_ID
    # post_message() never touches status — see ADR-0022 Decision 2.
    assert service.get_case_with_messages(case_id=case.id)[0].status is CaseStatus.OPEN


def test_post_message_raises_for_unknown_case(service: SupportService) -> None:
    with pytest.raises(SupportCaseNotFoundError):
        service.post_message(
            case_id=uuid.uuid4(),
            sender_type=SenderType.ADMIN,
            sender_id=ADMIN_ID,
            message="x",
            now=NOW,
        )


def test_assign_case_transitions_open_to_assigned(service: SupportService) -> None:
    case = _create_case(service)

    assigned = service.assign_case(case_id=case.id, admin_id=ADMIN_ID, now=NOW)

    assert assigned.status is CaseStatus.ASSIGNED
    assert assigned.assigned_admin_id == ADMIN_ID


def test_assign_case_rejects_when_not_open(service: SupportService) -> None:
    case = _create_case(service)
    service.assign_case(case_id=case.id, admin_id=ADMIN_ID, now=NOW)

    with pytest.raises(SupportCaseNotAssignableError):
        service.assign_case(case_id=case.id, admin_id=uuid.uuid4(), now=NOW)


def test_assign_case_raises_for_unknown_case(service: SupportService) -> None:
    with pytest.raises(SupportCaseNotFoundError):
        service.assign_case(case_id=uuid.uuid4(), admin_id=ADMIN_ID, now=NOW)


def test_resolve_case_from_open(service: SupportService) -> None:
    case = _create_case(service)

    resolved = service.resolve_case(case_id=case.id, now=NOW)

    assert resolved.status is CaseStatus.RESOLVED


def test_resolve_case_from_assigned(service: SupportService) -> None:
    case = _create_case(service)
    service.assign_case(case_id=case.id, admin_id=ADMIN_ID, now=NOW)

    resolved = service.resolve_case(case_id=case.id, now=NOW)

    assert resolved.status is CaseStatus.RESOLVED


def test_resolve_case_rejects_when_already_resolved(service: SupportService) -> None:
    case = _create_case(service)
    service.resolve_case(case_id=case.id, now=NOW)

    with pytest.raises(SupportCaseNotResolvableError):
        service.resolve_case(case_id=case.id, now=NOW)


def test_resolve_case_raises_for_unknown_case(service: SupportService) -> None:
    with pytest.raises(SupportCaseNotFoundError):
        service.resolve_case(case_id=uuid.uuid4(), now=NOW)


def test_get_case_with_messages_returns_case_and_thread(
    service: SupportService,
) -> None:
    case = _create_case(service, message="First message")
    service.post_message(
        case_id=case.id,
        sender_type=SenderType.ADMIN,
        sender_id=ADMIN_ID,
        message="Reply",
        now=NOW,
    )

    fetched_case, thread = service.get_case_with_messages(case_id=case.id)

    assert fetched_case.id == case.id
    assert [m.message for m in thread] == ["First message", "Reply"]


def test_get_case_with_messages_raises_for_unknown_case(
    service: SupportService,
) -> None:
    with pytest.raises(SupportCaseNotFoundError):
        service.get_case_with_messages(case_id=uuid.uuid4())
