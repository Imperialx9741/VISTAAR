"""FastAPI dependency wiring for Safety."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.safety.repositories import (
    SqlAlchemySafetyEventRepository,
    SqlAlchemySafetyIncidentRepository,
)
from modules.safety.service import SafetyService


def get_safety_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> SafetyService:
    return SafetyService(
        incidents=SqlAlchemySafetyIncidentRepository(db),
        events=SqlAlchemySafetyEventRepository(db),
    )
