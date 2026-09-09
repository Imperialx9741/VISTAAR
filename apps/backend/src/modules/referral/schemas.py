"""Pydantic request/response DTOs for Referral's HTTP surface."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AttachReferralRequest(BaseModel):
    """POST /api/v1/referrals/attach (api-contracts.md §38)."""

    code: str = Field(min_length=1, max_length=50)
