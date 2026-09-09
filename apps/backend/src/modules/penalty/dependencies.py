"""FastAPI dependency wiring for Penalty."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.penalty.repositories import (
    SqlAlchemyPenaltyRepository,
    SqlAlchemyStrikeRepository,
)
from modules.penalty.service import PenaltyService


def get_penalty_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> PenaltyService:
    return PenaltyService(
        penalties=SqlAlchemyPenaltyRepository(db),
        strikes=SqlAlchemyStrikeRepository(db),
    )
