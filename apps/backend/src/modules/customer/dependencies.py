"""FastAPI dependency wiring for Customer.

Reuses modules.identity.dependencies.require_customer as-is for
authentication/authorization — no new auth code in this module. /me
routes are inherently self-scoped (the authenticated account's own id is
always the resource id), so no separate resource-ownership check is
needed beyond "is this account a CUSTOMER" (require_customer already
enforces that).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.customer.repositories import SqlAlchemyCustomerRepository
from modules.customer.service import CustomerService


def get_customer_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> CustomerService:
    return CustomerService(customers=SqlAlchemyCustomerRepository(db))
