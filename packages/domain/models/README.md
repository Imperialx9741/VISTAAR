# VISTAAR Domain Models Directory

This directory is designated to store future core business domain entities, value objects, aggregates, and domain rules representing VISTAAR business logic.

## Future Directory Organization

When business domain models are introduced in future tasks, models should be organized logically by domain feature area:

```
models/
├── README.md
├── common/        # Shared domain value objects (e.g., GeoLocation, CurrencyAmount)
├── users/         # Customer profile domain entities & business rules
├── drivers/       # Driver status, verification & availability domain models
├── vehicles/      # Vehicle specification & capacity domain objects
├── rides/         # Ride lifecycle, trip state & estimation aggregates
├── matching/      # Match candidate evaluation & ranking domain logic
├── pricing/       # Fare calculation, surge pricing & fee calculation domain rules
├── payments/      # Wallet balance & transaction domain entities
└── safety/        # Incident alert & verification domain objects
```

## Domain Modeling Guidelines

1. **Technology Independence**: Domain models represent pure business concepts. They must **NOT** import:
   - Framework dependencies (FastAPI, Flask)
   - Persistence dependencies (SQLAlchemy, ORM mappers)
   - Messaging/caching dependencies (Kafka, Redis)
   - Network protocols (HTTP, REST, gRPC)
2. **Encapsulate Invariants**: Entities and aggregates protect their internal state by exposing explicit business methods rather than public mutable properties.
3. **Decoupled from API & Event Contracts**: Domain models represent internal core business logic. They do NOT double as external API request/response DTOs or event transport schemas.
