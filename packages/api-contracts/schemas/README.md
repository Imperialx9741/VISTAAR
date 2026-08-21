# VISTAAR API Contract Schemas Directory

This directory is designated to store future shared API request and response contract schema definitions between VISTAAR client applications (Customer Mobile, Driver Mobile, Admin Web) and backend services.

## Future Directory Organization

When business contracts are introduced in future tasks, schemas should be grouped logically by feature area:

```
schemas/
├── README.md
├── common/        # Shared baseline structures (Error responses, Pagination wrappers)
├── auth/          # Authentication & OTP contracts
├── users/         # Customer profile & account contracts
├── drivers/       # Driver onboarding, verification & status contracts
├── rides/         # Ride estimation, request, matching & status contracts
├── vehicles/      # Vehicle specification & management contracts
└── payments/      # Payment method, transaction & invoice contracts
```

## Schema Guidelines

1. **Decoupled from Database**: Schemas define external wire formats only and must NOT import database models, ORM classes, or internal domain logic.
2. **Explicit Nullability**: Fields must explicitly declare required vs optional states.
3. **Immutability & Purity**: Contract schemas represent immutable data transfer objects (DTOs).
