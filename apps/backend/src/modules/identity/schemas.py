"""Pydantic request/response DTOs for the Identity API.

Mirrors docs/05-api/api-contracts.md §6-7 request/response shapes for the
two documented endpoints, plus additional schemas for refresh/logout,
which are supported by security.md/domain-design.md but not yet spelled
out with example payloads in api-contracts.md — see this task's
documentation update to api-contracts.md for the additions.

These are the ONLY objects the router ever returns — internal domain
entities and ORM rows are never serialized directly back to the client
(task instruction: "Do not return internal database models directly").
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from modules.identity.domain.entities import AccountType


class OtpRequestBody(BaseModel):
    phone: str = Field(..., examples=["+919999999999"])
    account_type: AccountType


class OtpRequestData(BaseModel):
    challenge_id: str
    expires_in: int


class OtpVerifyBody(BaseModel):
    """Matches docs/05-api/api-contracts.md §7 exactly: {challenge_id, otp}.

    No account_type here — see domain/entities.py's OtpChallenge
    docstring for why it is not re-requested from the client at verify
    time.
    """

    challenge_id: str
    otp: str = Field(..., min_length=4, max_length=10)


class TokenPairData(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class RefreshBody(BaseModel):
    refresh_token: str


class LogoutBody(BaseModel):
    refresh_token: str | None = None


class MfaEnrollData(BaseModel):
    secret: str
    otpauth_uri: str


class MfaConfirmBody(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class MfaVerifyBody(BaseModel):
    mfa_token: str
    code: str = Field(..., min_length=6, max_length=6)


class MfaDisableBody(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
