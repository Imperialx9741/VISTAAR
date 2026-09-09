"""VISTAAR Customer module.

Owns the customer's business profile and preferences, per
docs/04-domain-design/domain-design.md §6 (Customer Domain) and
docs/04-database/database-design.md §6 (customer.customers,
customer.preferences).

Scope (Phase 2 / Task 2.2): Get Profile and Update Profile only. See the
approved plan for this task for what is deliberately out of scope
(DeactivateCustomer/ReactivateCustomer, CustomerCreated/CustomerProfileUpdated
events, ride history/promotions/outstanding-charges access, profile-photo
upload itself).

A customer.customers row is auto-provisioned on first access (see
service.py) rather than created by modules/identity/ reaching across
domain boundaries — technical-architecture.md §2.2 prohibits direct
cross-domain database writes, and no customer.* event exists in
event-contracts.md for Identity to publish instead. This keeps
modules/identity/ completely unaware of modules/customer/.

Layering mirrors modules/identity/ exactly:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        CustomerRepository Protocol
    models.py       SQLAlchemy ORM models (infrastructure)
    repositories.py SQLAlchemy-backed implementation of the port
    service.py      application service (use cases), incl. auto-provisioning
    schemas.py      Pydantic request/response DTOs
    dependencies.py FastAPI DI wiring (reuses modules.identity's auth
                    dependencies as-is — no new auth code here)
    router.py       FastAPI routes under /api/v1/customers
"""
