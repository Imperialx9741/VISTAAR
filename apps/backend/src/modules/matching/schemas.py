"""Pydantic request DTO for the Matching API.

Mirrors docs/05-api/api-contracts.md §15's "Driver Location Update"
request exactly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UpdateLocationBody(BaseModel):
    latitude: float
    longitude: float
    accuracy_meters: float | None = None
    recorded_at: datetime | None = None
