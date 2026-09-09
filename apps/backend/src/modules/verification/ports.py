"""Abstract interface (port) the application layer depends on.

Concrete implementation lives in repositories.py. Mirrors the other
modules' ports.py role.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from modules.verification.domain.entities import (
    Evidence,
    VerificationCase,
    VerificationResult,
)


class VerificationCaseRepository(Protocol):
    def create_case(self, case: VerificationCase) -> VerificationCase: ...

    def get_case(self, case_id: uuid.UUID) -> VerificationCase | None: ...

    def list_cases_for_subject(
        self, *, subject_type: str, subject_id: uuid.UUID
    ) -> list[VerificationCase]: ...

    def save_case(self, case: VerificationCase) -> None: ...

    def list_by_status(
        self, *, status: str | None, offset: int, limit: int
    ) -> tuple[list[VerificationCase], int]:
        """Admin Web §4.4's pending-review queue, across every subject
        (driver + vehicle documents) — unlike list_cases_for_subject(),
        not scoped to one subject_type/subject_id. `status` omitted
        returns every case; the Admin Web's own queue screen is expected
        to default its own query to status=PENDING client-side."""
        ...

    def add_evidence(self, evidence: Evidence) -> Evidence: ...

    def list_evidence_for_case(self, case_id: uuid.UUID) -> list[Evidence]: ...

    def add_result(self, result: VerificationResult) -> VerificationResult: ...
