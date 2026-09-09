"""FastAPI dependency wiring for Verification.

No router exists for this module (ADR-0008 item 2 — no admin/HTTP
surface yet), so this factory is consumed by other modules' routers
(currently only modules/driver/router.py) via the same
API-layer-composition pattern used for driver+vehicle elsewhere in this
codebase — never via a direct modules.verification import from another
module's domain/service layer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from core.database import get_db
from modules.verification.providers import get_verification_provider
from modules.verification.repositories import SqlAlchemyVerificationCaseRepository
from modules.verification.service import VerificationService


def get_verification_service(
    db: Annotated[DbSession, Depends(get_db)],
) -> VerificationService:
    return VerificationService(
        cases=SqlAlchemyVerificationCaseRepository(db),
        provider=get_verification_provider(),
    )
