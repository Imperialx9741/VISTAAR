from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from core.config import settings

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    # Standard settings for development/production stability
    pool_pre_ping=True,
)

# Reusable session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base class for metadata definition
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a transactional database session.

    Commits on successful completion of the request, rolls back on any
    exception, and always closes the session. Discovered and fixed during
    Phase 2 / Task 2.1 (Identity & Authentication Foundation): the
    original version yielded the session without ever committing, so any
    write made through it (e.g. modules/identity's account/OTP/session
    rows) was silently rolled back on session close instead of persisted
    — nothing before this task exercised a write through this dependency,
    which is why it went unnoticed.

    Yields:
        Session: A SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
