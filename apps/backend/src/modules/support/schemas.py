"""Pydantic request DTOs for the Support API.

Mirrors docs/05-api/api-contracts.md §44's "Create Support Case" request
exactly.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class CreateSupportCaseBody(BaseModel):
    category: str | None = None
    ride_id: uuid.UUID | None = None
    message: str
