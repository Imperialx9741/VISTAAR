"""Pydantic request/response DTOs for the Notification API (ADR-0052)."""

from __future__ import annotations

from pydantic import BaseModel

from modules.notification.domain.entities import Platform


class RegisterDeviceBody(BaseModel):
    platform: Platform
    token: str
