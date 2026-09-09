"""Pydantic request/response DTOs for the Customer API.

Mirrors docs/05-api/api-contracts.md §8 — extended in this same change
with a documented response example and two additional optional PATCH
fields (profile_photo_uri, notification_enabled), the only other
customer-owned fields that exist anywhere in the schema.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UpdateCustomerProfileBody(BaseModel):
    """All fields optional — PATCH semantics. router.py converts this to
    service.ProfileUpdate via model_dump(exclude_unset=True) so an
    omitted field is left untouched, not cleared."""

    full_name: str | None = Field(default=None, examples=["Customer Name"])
    profile_photo_uri: str | None = None
    language: str | None = Field(default=None, examples=["en"])
    notification_enabled: bool | None = None
