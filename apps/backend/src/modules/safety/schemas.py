"""Pydantic request DTOs for the Safety API.

Mirrors docs/05-api/api-contracts.md §41's "SOS" request exactly.
"""

from __future__ import annotations

from pydantic import BaseModel


class SosRequest(BaseModel):
    incident_type: str
    latitude: float
    longitude: float
