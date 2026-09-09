"""SQLAlchemy-backed implementations of the repository ports.

Translates between the ORM rows (models.py) and the pure domain entities
(domain/entities.py) — the application layer (service.py) only ever sees
domain entities, never ORM objects, per packages/domain/README.md §3.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from modules.identity.domain.entities import (
    Account,
    AccountStatus,
    AccountType,
    MfaCredential,
    MfaCredentialStatus,
    OtpChallenge,
    OtpChallengeStatus,
    Session,
)
from modules.identity.models import (
    AccountORM,
    MfaCredentialORM,
    OtpChallengeORM,
    SessionORM,
)


def _account_from_orm(row: AccountORM) -> Account:
    return Account(
        id=row.id,
        account_type=AccountType(row.account_type),
        phone=row.phone,
        status=AccountStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _challenge_from_orm(row: OtpChallengeORM) -> OtpChallenge:
    return OtpChallenge(
        id=row.id,
        account_id=row.account_id,
        account_type=AccountType(row.account_type),
        phone=row.phone,
        otp_hash=row.otp_hash,
        expires_at=row.expires_at,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        status=OtpChallengeStatus(row.status),
        created_at=row.created_at,
    )


def _credential_from_orm(row: MfaCredentialORM) -> MfaCredential:
    return MfaCredential(
        account_id=row.account_id,
        secret=row.secret,
        status=MfaCredentialStatus(row.status),
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
    )


def _session_from_orm(row: SessionORM) -> Session:
    return Session(
        id=row.id,
        account_id=row.account_id,
        refresh_token_hash=row.refresh_token_hash,
        device_metadata=row.device_metadata,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


class SqlAlchemyAccountRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get_by_phone(self, phone: str) -> Account | None:
        row = self._db.execute(
            select(AccountORM).where(AccountORM.phone == phone)
        ).scalar_one_or_none()
        return _account_from_orm(row) if row else None

    def get_by_id(self, account_id: uuid.UUID) -> Account | None:
        row = self._db.get(AccountORM, account_id)
        return _account_from_orm(row) if row else None

    def create(self, *, account_type: AccountType, phone: str) -> Account:
        row = AccountORM(
            id=uuid.uuid4(),
            account_type=account_type.value,
            phone=phone,
            status=AccountStatus.ACTIVE.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _account_from_orm(row)


class SqlAlchemyOtpChallengeRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, challenge: OtpChallenge) -> OtpChallenge:
        row = OtpChallengeORM(
            id=challenge.id,
            account_id=challenge.account_id,
            account_type=challenge.account_type.value,
            phone=challenge.phone,
            otp_hash=challenge.otp_hash,
            expires_at=challenge.expires_at,
            attempts=challenge.attempts,
            max_attempts=challenge.max_attempts,
            status=challenge.status.value,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _challenge_from_orm(row)

    def get_by_id(self, challenge_id: uuid.UUID) -> OtpChallenge | None:
        row = self._db.get(OtpChallengeORM, challenge_id)
        return _challenge_from_orm(row) if row else None

    def invalidate_active_for_phone(self, phone: str) -> None:
        rows = (
            self._db.execute(
                select(OtpChallengeORM).where(
                    OtpChallengeORM.phone == phone,
                    OtpChallengeORM.status == OtpChallengeStatus.ACTIVE.value,
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.status = OtpChallengeStatus.INVALIDATED.value
        self._db.flush()

    def save(self, challenge: OtpChallenge) -> None:
        row = self._db.get(OtpChallengeORM, challenge.id)
        if row is None:
            raise LookupError(f"OtpChallenge {challenge.id} not found")
        row.attempts = challenge.attempts
        row.status = challenge.status.value
        row.account_id = challenge.account_id
        self._db.flush()

    def count_active_for_phone_since(self, phone: str, since: datetime) -> int:
        result = self._db.execute(
            select(func.count())
            .select_from(OtpChallengeORM)
            .where(
                OtpChallengeORM.phone == phone,
                OtpChallengeORM.created_at >= since,
            )
        ).scalar_one()
        return int(result)


class SqlAlchemySessionRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def create(self, session: Session) -> Session:
        row = SessionORM(
            id=session.id,
            account_id=session.account_id,
            refresh_token_hash=session.refresh_token_hash,
            device_metadata=session.device_metadata,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
        )
        self._db.add(row)
        self._db.flush()
        self._db.refresh(row)
        return _session_from_orm(row)

    def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        row = self._db.get(SessionORM, session_id)
        return _session_from_orm(row) if row else None

    def get_by_refresh_token_hash(self, token_hash: str) -> Session | None:
        row = self._db.execute(
            select(SessionORM).where(SessionORM.refresh_token_hash == token_hash)
        ).scalar_one_or_none()
        return _session_from_orm(row) if row else None

    def save(self, session: Session) -> None:
        row = self._db.get(SessionORM, session.id)
        if row is None:
            raise LookupError(f"Session {session.id} not found")
        row.revoked_at = session.revoked_at
        self._db.flush()

    def revoke(self, session_id: uuid.UUID) -> None:
        row = self._db.get(SessionORM, session_id)
        if row is None:
            raise LookupError(f"Session {session_id} not found")
        row.revoked_at = datetime.now(UTC)
        self._db.flush()


class SqlAlchemyMfaCredentialRepository:
    """ADR-0051 — identity.mfa_credentials, account_id as primary key."""

    def __init__(self, db: DbSession) -> None:
        self._db = db

    def get(self, account_id: uuid.UUID) -> MfaCredential | None:
        row = self._db.get(MfaCredentialORM, account_id)
        return _credential_from_orm(row) if row else None

    def get_for_update(self, account_id: uuid.UUID) -> MfaCredential | None:
        row = self._db.execute(
            select(MfaCredentialORM)
            .where(MfaCredentialORM.account_id == account_id)
            .with_for_update()
        ).scalar_one_or_none()
        return _credential_from_orm(row) if row else None

    def upsert(self, credential: MfaCredential) -> MfaCredential:
        row = self._db.get(MfaCredentialORM, credential.account_id)
        if row is None:
            row = MfaCredentialORM(account_id=credential.account_id)
            self._db.add(row)
        row.secret = credential.secret
        row.status = credential.status.value
        row.confirmed_at = credential.confirmed_at
        self._db.flush()
        self._db.refresh(row)
        return _credential_from_orm(row)

    def save(self, credential: MfaCredential) -> None:
        row = self._db.get(MfaCredentialORM, credential.account_id)
        if row is None:
            raise LookupError(f"MfaCredential {credential.account_id} not found")
        row.secret = credential.secret
        row.status = credential.status.value
        row.confirmed_at = credential.confirmed_at
        self._db.flush()

    def delete(self, account_id: uuid.UUID) -> None:
        row = self._db.get(MfaCredentialORM, account_id)
        if row is not None:
            self._db.delete(row)
            self._db.flush()
