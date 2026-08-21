# VISTAAR API Contracts Package

This package defines the shared API request/response contract foundation and conventions between VISTAAR client applications (**Customer Mobile**, **Driver Mobile**, **Admin Web**) and backend API services.

---

## 1. Purpose & Scope

The primary purpose of `api-contracts` is to establish a single source of truth for all external HTTP/REST network payloads exchanged across the VISTAAR platform ecosystem.

### What Belongs Here
- **Request Contracts**: Structural specifications for request bodies, query parameters, and header expectations.
- **Response Contracts**: Structural specifications for successful API response payloads.
- **Error Response Contracts**: Structured formats for application-level error payloads.
- **Shared Enums & Constants**: Public API enumeration values (e.g. status strings, error codes).

### What Does NOT Belong Here
- **Database Models / ORM Classes**: SQLAlchemy tables, database entities, or migration scripts.
- **Backend Services & Business Logic**: Route handlers, database queries, ORM operations, or background workers.
- **Kafka & Event Contracts**: Asynchronous message event definitions (belong in `packages/event-contracts/`).
- **Infrastructure & Client Connections**: Redis connections, database sessions, or HTTP client instances.
- **Authentication Credentials**: Passwords, tokens, JWT keys, or API secrets.

---

## 2. Architectural Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                 VISTAAR Client Applications                 │
│    (Customer Mobile  •  Driver Mobile  •  Admin Web)       │
└──────────────────────────────┬──────────────────────────────┘
                               │ Consumes Shared Contracts
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 packages/api-contracts/                    │
│   (Request Schemas  •  Response Schemas  •  Error Shapes)  │
└──────────────────────────────▲──────────────────────────────┘
                               │ Implements & Validates
                               │
┌──────────────────────────────┴──────────────────────────────┐
│                    VISTAAR Backend API                      │
│                  (FastAPI Application)                      │
└─────────────────────────────────────────────────────────────┘
```

* **Backend**: Uses contract schemas to validate incoming payloads and serialize responses.
* **Client Applications**: Consume contract schemas to type-check API requests and responses.
* **`packages/domain/`**: Contains core domain entities. API contract models adapt external inputs before passing them into domain services.
* **`packages/validation/`**: Defines custom business validation rules applied on top of contract schemas.

---

## 3. API Contract Conventions

### Wire Format & Encoding
* **Format**: Standard **JSON** (`application/json`).
* **Encoding**: UTF-8.

### Naming Conventions
* **JSON Properties**: `camelCase` (e.g., `passengerId`, `pickupLocation`, `createdAt`).
* **Contract Schema Classes**: `PascalCase` (e.g., `RideRequest`, `DriverResponse`).
* **Enum Values**: `UPPER_SNAKE_CASE` or explicit string values.

### Request Contracts
* Every mutative API request (POST, PUT, PATCH) must define a dedicated Request Contract.
* Required vs Optional fields must be explicitly declared.
* All incoming strings must be trimmed of accidental leading/trailing whitespace.

### Response Contracts
* Every API endpoint must return a structured, predictable payload shape.
* Data fields should use consistent scalar types (ISO 8601 UTC strings for timestamps, decimal/float for monetary values, string UUIDs for identifiers).

### Standard Error Response Shape (Conceptual)
Future API error responses will follow a uniform structured shape containing:
```json
{
  "error": {
    "code": "RIDE_NOT_FOUND",
    "message": "The requested ride identifier does not exist or has expired.",
    "details": {},
    "requestId": "req_123456789"
  }
}
```

---

## 4. API Versioning & Backward Compatibility

### Versioning Convention
* All future business API endpoints must be scoped under a versioned path prefix:
  `/api/v1/...`
* Infrastructure health check endpoints remain un-versioned (`/health`, `/health/db`, `/health/redis`, `/health/kafka`).

### Backward Compatibility Expectations
* **Non-Breaking Updates**: Adding optional fields or new endpoints is non-breaking.
* **Breaking Updates**: Removing fields, altering field types, or making optional fields required constitutes a breaking change and requires incrementing the API version (`/api/v2/...`).

---

## 5. Introducing Future Contracts

When business features are introduced in future tasks:
1. Create a schema module under `packages/api-contracts/schemas/<feature_area>/`.
2. Define explicit request and response models.
3. Ensure no database or backend framework imports are used.
