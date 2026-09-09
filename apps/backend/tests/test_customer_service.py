"""Unit tests for CustomerService against an in-memory fake repository."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from modules.customer.domain.entities import Customer
from modules.customer.domain.errors import InvalidLanguageError
from modules.customer.service import CustomerService


class FakeCustomerRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Customer] = {}

    def get_by_id(self, customer_id: uuid.UUID) -> Customer | None:
        return self.by_id.get(customer_id)

    def create(self, customer: Customer) -> Customer:
        self.by_id[customer.id] = customer
        return customer

    def save(self, customer: Customer) -> None:
        self.by_id[customer.id] = customer

    def search(
        self, *, query: str | None, offset: int, limit: int
    ) -> tuple[list[Customer], int]:
        matches = sorted(
            (
                c
                for c in self.by_id.values()
                if query is None
                or (c.full_name is not None and query.lower() in c.full_name.lower())
            ),
            key=lambda c: c.created_at,
            reverse=True,
        )
        return matches[offset : offset + limit], len(matches)

    def count_total(self) -> int:
        return len(self.by_id)

    def count_created_in_range(self, *, since: datetime, until: datetime) -> int:
        return sum(1 for c in self.by_id.values() if since <= c.created_at < until)

    def list_all_ids(self) -> list[uuid.UUID]:
        return list(self.by_id.keys())


@pytest.fixture
def repo() -> FakeCustomerRepository:
    return FakeCustomerRepository()


@pytest.fixture
def service(repo: FakeCustomerRepository) -> CustomerService:
    return CustomerService(customers=repo)


ACCOUNT_ID = uuid.uuid4()


def test_get_profile_auto_provisions_with_defaults(
    service: CustomerService, repo: FakeCustomerRepository
) -> None:
    assert ACCOUNT_ID not in repo.by_id

    customer = service.get_profile(account_id=ACCOUNT_ID)

    assert customer.id == ACCOUNT_ID
    assert customer.full_name is None
    assert customer.language == "en"
    assert customer.notification_enabled is True
    assert ACCOUNT_ID in repo.by_id


def test_get_profile_is_idempotent_after_provisioning(
    service: CustomerService, repo: FakeCustomerRepository
) -> None:
    first = service.get_profile(account_id=ACCOUNT_ID)
    second = service.get_profile(account_id=ACCOUNT_ID)

    assert first.id == second.id
    assert len(repo.by_id) == 1


def test_update_profile_auto_provisions_if_missing(
    service: CustomerService, repo: FakeCustomerRepository
) -> None:
    customer = service.update_profile(
        account_id=ACCOUNT_ID, update={"full_name": "Jane Doe"}
    )

    assert customer.full_name == "Jane Doe"
    assert ACCOUNT_ID in repo.by_id


def test_update_profile_only_changes_supplied_fields(
    service: CustomerService, repo: FakeCustomerRepository
) -> None:
    service.update_profile(
        account_id=ACCOUNT_ID,
        update={"full_name": "Jane Doe", "language": "hi"},
    )

    updated = service.update_profile(
        account_id=ACCOUNT_ID, update={"notification_enabled": False}
    )

    assert updated.full_name == "Jane Doe"  # untouched by the second call
    assert updated.language == "hi"  # untouched by the second call
    assert updated.notification_enabled is False  # changed


def test_update_profile_can_clear_nullable_fields(
    service: CustomerService, repo: FakeCustomerRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Jane Doe"})

    cleared = service.update_profile(account_id=ACCOUNT_ID, update={"full_name": None})

    assert cleared.full_name is None


def test_update_profile_rejects_invalid_language(
    service: CustomerService, repo: FakeCustomerRepository
) -> None:
    with pytest.raises(InvalidLanguageError):
        service.update_profile(account_id=ACCOUNT_ID, update={"language": "fr"})


def test_get_profile_reflects_prior_update(
    service: CustomerService, repo: FakeCustomerRepository
) -> None:
    service.update_profile(account_id=ACCOUNT_ID, update={"full_name": "Jane Doe"})

    fetched = service.get_profile(account_id=ACCOUNT_ID)

    assert fetched.full_name == "Jane Doe"
