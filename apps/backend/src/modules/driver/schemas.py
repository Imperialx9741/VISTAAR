"""Pydantic request DTOs for the Driver API.

Mirrors docs/05-api/api-contracts.md §9 — extended in this same change
with a documented response example. No response model class is defined
here; router.py builds the response dict directly, same convention as
modules.identity.router and modules.customer.router.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UpdateDriverProfileBody(BaseModel):
    """All fields optional at the Pydantic level — PATCH semantics via
    model_dump(exclude_unset=True), same convention as
    modules.customer.schemas.UpdateCustomerProfileBody. Note that
    service.py's DriverService.update_profile() still requires full_name
    to be present in the *first* update for a given account (see that
    module's docstring) — this schema does not encode that conditional
    requirement, since it only applies when no profile exists yet."""

    full_name: str | None = None
    profile_photo_uri: str | None = None


class SubmitDriverDocumentBody(BaseModel):
    """Mirrors api-contracts.md §9's "Submit Driver Document" request
    exactly, plus optional expires_at (documented on the
    driver.documents column, database-design.md §7.2, but not shown in
    the request example). document_type has no canonical enum — see
    ADR-0007."""

    document_type: str
    document_number: str | None = None
    evidence_uri: str | None = None
    expires_at: datetime | None = None


class RequestUploadUrlBody(BaseModel):
    """ADR-0031 (2026-08-25). content_type must be one of
    shared.storage's allow-listed MIME types (image/jpeg, image/png,
    image/webp, application/pdf) — validated at the service/storage
    layer, not here, same "shape here, business/domain validation
    downstream" split every other body in this module already follows."""

    content_type: str
