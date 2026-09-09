"""Pydantic request DTOs for the Vehicle API.

Mirrors docs/05-api/api-contracts.md §11's "Add Vehicle" and "Update
Vehicle" requests, extended with `cab_tier` (ADR-0020 Decision 1) —
required when `category` is `CAB`, must be omitted/null otherwise;
VehicleService.add_vehicle() -> Vehicle.new() -> validate_cab_tier()
enforces this, not Pydantic.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AddVehicleBody(BaseModel):
    category: str
    cab_tier: str | None = None
    registration_number: str
    make: str | None = None
    model: str | None = None


class UpdateVehicleBody(BaseModel):
    """Only make/model — see api-contracts.md §11 ("Update Vehicle") for
    why driver_id/category/registration_number/verification_status/
    operational_status/timestamps are not accepted here."""

    make: str | None = None
    model: str | None = None


class SubmitVehicleDocumentBody(BaseModel):
    """Mirrors modules.driver.schemas.SubmitDriverDocumentBody field-for-
    field (ADR-0072, 2026-09-04) — same "no canonical document_type
    vocabulary" treatment (ADR-0007 item A, still open)."""

    document_type: str
    document_number: str | None = None
    evidence_uri: str | None = None
    expires_at: datetime | None = None
