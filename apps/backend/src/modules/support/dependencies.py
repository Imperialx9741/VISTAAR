"""FastAPI dependency wiring for Support."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.support.repositories import (
    SqlAlchemySupportCaseRepository,
    SqlAlchemySupportMessageRepository,
)
from modules.support.service import SupportService


def get_support_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> SupportService:
    return SupportService(
        cases=SqlAlchemySupportCaseRepository(db),
        messages=SqlAlchemySupportMessageRepository(db),
    )
