# VISTAAR Event Contracts Package

This package defines the shared asynchronous event contract foundation and conventions for event-driven message payloads across VISTAAR microservices, message streams (e.g. Kafka topics), and background event handlers.

---

## 1. Purpose & Scope

The primary purpose of `event-contracts` is to establish a single source of truth for all asynchronous message payloads and domain event structures emitted and consumed within the VISTAAR ecosystem.

### What Belongs Here
- **Event Schemas**: Data transfer objects (DTOs) defining the exact payload structure of asynchronous events.
- **Event Envelopes**: Standardized outer wrapper structure for message headers, routing metadata, and correlation tracking.
- **Event Type Enumerations**: Canonical string identifiers for platform domain events.

### What Does NOT Belong Here
- **Kafka Client Infrastructure**: Connection handling, producers, consumers, or admin clients (located in `apps/backend/src/core/kafka.py`).
- **Kafka Topic Creation / Broker Config**: Infrastructure topic setup scripts or broker configs.
- **Database Models / ORM Classes**: SQLAlchemy entities, database schemas, or migrations.
- **Synchronous API Contracts**: HTTP REST request/response schemas (located in `packages/api-contracts/`).
- **Message Handlers & Listeners**: Business event processing logic or background consumers.

---

## 2. Architectural Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                   Asynchronous Event Stream                 │
│                 (Kafka Broker Infrastructure)               │
└──────────────────────────────▲──────────────────────────────┘
                               │ Carries Event Payloads
                               │
┌──────────────────────────────┴──────────────────────────────┐
│                packages/event-contracts/                    │
│    (Standard Envelopes  •  Event Payloads  •  Event Types)  │
└──────────────────────────────▲──────────────────────────────┘
                               │ Implements / Consumes
                               │
┌──────────────────────────────┴──────────────────────────────┐
│                    VISTAAR Backend Services                 │
│         (Event Producers  •  Event Consumers  •  Workers)   │
└─────────────────────────────────────────────────────────────┘
```

* **Difference from API Contracts**:
  * **API Contracts (`packages/api-contracts/`)**: Govern synchronous request/response HTTP REST communication between client apps and backend APIs.
  * **Event Contracts (`packages/event-contracts/`)**: Govern asynchronous event-driven message streams broadcasted across background services and event consumers.
* **Domain Package (`packages/domain/`)**: Core domain entities trigger business domain events. Event contract models encapsulate these events for external message transport.
* **Validation Package (`packages/validation/`)**: Validates event payload integrity before publishing to or processing from message brokers.

---

## 3. Conceptual Event Envelope

All asynchronous event messages across VISTAAR adhere to a standard conceptual outer envelope structure:

```json
{
  "eventId": "evt_9876543210_abc",
  "eventType": "RideRequested",
  "eventVersion": 1,
  "occurredAt": "2026-08-20T11:45:00Z",
  "source": "vistaar.backend.ride-service",
  "correlationId": "corr_123456789",
  "payload": {},
  "metadata": {}
}
```

### Key Envelope Attributes
* **`eventId`**: Unique string identifier for the specific event instance (used for consumer deduplication/idempotency).
* **`eventType`**: Canonical name of the domain event.
* **`eventVersion`**: Integer schema version of the payload (starts at `1`).
* **`occurredAt`**: ISO 8601 UTC timestamp indicating when the event occurred.
* **`source`**: Identifier of the producing service or component.
* **`correlationId`**: Distributed tracing identifier spanning request-to-event workflows.
* **`payload`**: Specific event data payload object.
* **`metadata`**: Optional execution metadata (e.g. environment, tenant ID).

---

## 4. Event Naming Conventions

* **Format**: `<Domain><Action>` in `PascalCase` past tense or state change (e.g., `RideRequested`, `DriverLocationUpdated`, `PaymentCompleted`).
* **Illustrative Examples** *(Architecture concepts only — not implemented in code)*:
  * `RideRequested`, `DriverAssigned`, `PaymentCompleted`, `UserRegistered`.

---

## 5. Serialization & Wire Format

* **Format**: Standard **JSON** (`application/json`).
* **Encoding**: UTF-8.

---

## 6. Versioning, Schema Evolution & Backward Compatibility

### Versioning Rules
* Every event contract includes an explicit `eventVersion` field.
* **Backward Compatible Changes**: Adding optional fields or metadata properties is non-breaking and retains `eventVersion: 1`.
* **Incompatible Breaking Changes**: Removing fields, renaming fields, or modifying field data types constitutes a breaking change and requires incrementing to `eventVersion: 2`.

### Idempotency Considerations
* Microservice consumers must handle potential duplicate message deliveries gracefully.
* Consumers should record processed `eventId` keys or leverage payload natural keys to guarantee idempotent message processing.

---

## 7. Introducing Future Event Contracts

When business events are introduced in future tasks:
1. Create a schema module under `packages/event-contracts/schemas/<feature_area>/`.
2. Inherit from the baseline Event Envelope structure.
3. Keep event schemas clean of Kafka client dependencies, ORM imports, or database connections.
