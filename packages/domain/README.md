# VISTAAR Domain Package

This package defines the core business domain architecture, modeling conventions, and boundaries for VISTAAR's business logic.

---

## 1. Purpose & Technology Independence

The primary purpose of `domain` is to house VISTAAR's core business concepts, rules, invariants, and domain entities independently of infrastructure, databases, frameworks, or external communication protocols.

### Pure Technology Independence
The domain layer must remain **100% technology-independent**. It must **NEVER** import or depend on:
- **Web Frameworks**: FastAPI, Starlette, Uvicorn.
- **ORM / Persistence**: SQLAlchemy, psycopg2, database sessions.
- **Messaging & Caching**: Kafka (`aiokafka`), Redis.
- **Frontend Frameworks**: Flutter, Next.js, React.
- **Infrastructure Code**: Docker, environment configurations, cloud SDKs.

---

## 2. Core Domain Modeling Concepts

```
┌─────────────────────────────────────────────────────────────┐
│                        Aggregate                            │
│  ┌────────────────────────┐    ┌─────────────────────────┐  │
│  │     Root Entity        │───►│      Value Object       │  │
│  │ (Identity & Invariants)│    │(Immutable & Value-Eq)   │  │
│  └────────────────────────┘    └─────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────┘
                               │ Triggers State Change
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      Domain Event                           │
│       (Internal Business Transition Notification)           │
└─────────────────────────────────────────────────────────────┘
```

### 1. Entities
- Objects defined by a unique, persistent **Identity** (`Id`) rather than their attributes.
- Maintain a distinct **Lifecycle** over time (e.g., created, updated, deactivated).
- Responsible for maintaining internal invariants and state transitions.

### 2. Value Objects
- Descriptive domain attributes defined entirely by their property values rather than an identity.
- **Immutable**: Any modification returns a new Value Object instance.
- Compared by value equality (e.g. monetary amounts, geographic coordinates, phone numbers).

### 3. Aggregates
- A cluster of associated Entities and Value Objects bound together by a single **Aggregate Root Entity**.
- Define an explicit **Consistency Boundary**: all internal business invariants must be satisfied before state modifications are committed.

### 4. Domain Services
- Stateless operations encapsulating complex business logic or rules that do not naturally belong to a single Entity or Value Object (e.g. complex surge pricing calculations or multi-candidate matching logic).

### 5. Domain Events
- Internal notifications representing a significant state change or business occurrence within the domain.
- Decoupled from external event transport packages.

---

## 3. Architectural Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                 packages/api-contracts/                    │
│            (External HTTP Request/Response DTOs)            │
└──────────────────────────────┬──────────────────────────────┘
                               │ Maps to Domain Inputs
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    packages/domain/                         │
│       (Core Domain Entities, Rules & Invariants)           │
└──────────────────────────────▲──────────────────────────────┘
                               │ Maps to Persistence
                               │
┌──────────────────────────────┴──────────────────────────────┐
│                    SQLAlchemy Database                      │
│            (Infrastructure ORM Tables & Schemas)            │
└─────────────────────────────────────────────────────────────┘
```

* **API Contracts (`packages/api-contracts/`)**: Define external HTTP REST wire formats. API contracts adapt user inputs into domain models.
* **Event Contracts (`packages/event-contracts/`)**: Define external asynchronous message envelopes for Kafka transport. Domain Events are mapped to Event Contracts at the infrastructure boundary.
* **Validation (`packages/validation/`)**: Contains reusable validation logic. Input validation happens at the API boundary before hitting domain invariants.
* **Infrastructure / ORM**: Database tables (SQLAlchemy) map to/from domain entities. Domain entities are **never** inherited from SQLAlchemy `Base`.

---

## 4. Introducing Future Domain Models

When business domain features are introduced in future tasks:
1. Create domain modules under `packages/domain/models/<feature_area>/`.
2. Model business concepts as pure Python entities and value objects.
3. Ensure zero imports of web, database, or infrastructure libraries.
