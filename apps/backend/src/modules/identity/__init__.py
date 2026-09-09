"""VISTAAR Identity & Authentication module.

Owns account identity, phone+OTP authentication, and session/token
lifecycle, per docs/04-domain-design/domain-design.md §5 (Identity Domain)
and docs/03-architecture/technical-architecture.md §5.1.

This module explicitly does NOT own (see domain-design.md §5.6):
- Ride state
- Driver wallet
- Fare
- Promotions
- Driver verification result

Layering (mirrors the technology-independence convention documented in
packages/domain/README.md, applied locally to this module since
packages/domain/ has no code yet):

    domain/         pure business logic — no FastAPI/SQLAlchemy/Redis imports
    ports.py        abstract interfaces the application layer depends on
    config.py       named configuration values (see module docstring there
                     for which values are approved business rules vs.
                     engineering configuration)
    models.py       SQLAlchemy ORM models (infrastructure)
    repositories.py SQLAlchemy-backed implementations of the ports
    sms.py          SmsProvider abstraction + development adapter
    security.py     OTP hashing, JWT issuance/verification, token hashing
    rate_limit.py   Redis-backed OTP request rate limiting
    token_denylist.py  Redis-backed access-token revocation on logout
    service.py      application services (use cases) orchestrating the above
    schemas.py      Pydantic request/response DTOs for the API layer
    dependencies.py FastAPI dependencies (get_current_account, require_role)
    router.py       FastAPI routes under /api/v1/auth
"""
