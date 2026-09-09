"""Application service (use cases) for Customer.

get_profile/update_profile take the already-authenticated identity
Account's id (from modules.identity.dependencies.get_current_account) as
a plain uuid.UUID — this module has no import dependency on
modules/identity/ at all, keeping the direction of coupling one-way (API
layer -> both modules; not module -> module).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TypedDict

from modules.customer.domain.entities import Customer
from modules.customer.domain.entities import validate_full_name as _validate_full_name
from modules.customer.domain.entities import validate_language as _validate_language
from modules.customer.domain.entities import (
    validate_profile_photo_uri as _validate_profile_photo_uri,
)
from modules.customer.domain.errors import CustomerNotFoundError
from modules.customer.ports import CustomerRepository


class ProfileUpdate(TypedDict, total=False):
    """Only keys actually present are applied — PATCH semantics.

    router.py builds this from schemas.UpdateCustomerProfileBody via
    ``model_dump(exclude_unset=True)``, so a field the client omitted
    from the JSON body never appears here at all (and is left
    unchanged), while a field explicitly sent as ``null`` appears with
    value ``None`` (and clears that column, for the nullable fields).
    """

    full_name: str | None
    profile_photo_uri: str | None
    language: str
    notification_enabled: bool


class CustomerService:
    def __init__(self, *, customers: CustomerRepository) -> None:
        self._customers = customers

    def get_profile(self, *, account_id: uuid.UUID) -> Customer:
        customer, _created = self._get_or_provision(account_id)
        return customer

    def get_or_provision_profile(
        self, *, account_id: uuid.UUID
    ) -> tuple[Customer, bool]:
        """Same lookup as get_profile(), but also reports whether this
        call is the one that created the customer.customers row. Exists
        only so modules/customer/router.py's GET /api/v1/customers/me
        can compose modules.promotion.grant_welcome_promotion() exactly
        once, at genuine first access (ADR-0019 Decision 4) — this
        service itself never imports modules.promotion (composition
        stays at the router layer, like every other cross-module call in
        this codebase)."""
        return self._get_or_provision(account_id)

    def update_profile(
        self, *, account_id: uuid.UUID, update: ProfileUpdate
    ) -> Customer:
        customer, _created = self._get_or_provision(account_id)

        if "full_name" in update:
            customer.full_name = _validate_full_name(update["full_name"])
        if "profile_photo_uri" in update:
            customer.profile_photo_uri = _validate_profile_photo_uri(
                update["profile_photo_uri"]
            )
        if "language" in update:
            validated_language = _validate_language(update["language"])
            if validated_language is not None:
                customer.language = validated_language
        if "notification_enabled" in update:
            customer.notification_enabled = update["notification_enabled"]

        customer.updated_at = datetime.now(UTC)
        self._customers.save(customer)
        return customer

    # --- Admin (Admin Web §4.1) ------------------------------------------

    def get_customer_for_admin(self, customer_id: uuid.UUID) -> Customer:
        customer = self._customers.get_by_id(customer_id)
        if customer is None:
            raise CustomerNotFoundError(f"No customer found for {customer_id}.")
        return customer

    def search_customers(
        self, *, query: str | None, offset: int, limit: int
    ) -> tuple[list[Customer], int]:
        return self._customers.search(query=query, offset=offset, limit=limit)

    # --- Reports (Admin Web §4.16, ADR-0047) -------------------------

    def count_total_customers(self) -> int:
        return self._customers.count_total()

    def count_new_customers_in_range(self, *, since: datetime, until: datetime) -> int:
        return self._customers.count_created_in_range(since=since, until=until)

    # --- Notification Broadcast (Admin Web §4.12, ADR-0055) -----------

    def list_all_customer_ids(self) -> list[uuid.UUID]:
        """The "All customers" audience — every customer_id,
        unpaginated."""
        return self._customers.list_all_ids()

    def _get_or_provision(self, account_id: uuid.UUID) -> tuple[Customer, bool]:
        existing = self._customers.get_by_id(account_id)
        if existing is not None:
            return existing, False
        new_customer = Customer.new(account_id, now=datetime.now(UTC))
        return self._customers.create(new_customer), True
