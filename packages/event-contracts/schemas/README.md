# VISTAAR Event Contract Schemas Directory

This directory is designated to store future shared asynchronous event payload contract definitions exchanged between VISTAAR microservices, background workers, and message streams (e.g., Kafka topics).

## Future Directory Organization

When business event contracts are introduced in future tasks, event schemas should be grouped logically by feature domain:

```
schemas/
├── README.md
├── common/        # Shared baseline event envelope definitions & headers
├── auth/          # Authentication & security audit events
├── users/         # Customer account lifecycle events
├── drivers/       # Driver location, availability & status events
├── rides/         # Ride lifecycle events (requested, matched, started, completed)
├── matching/      # Match engine dispatch & candidate events
├── payments/      # Transaction processing & wallet balance events
└── notifications/ # Push notification & SMS dispatch events
```

## Schema Guidelines

1. **Decoupled from Infrastructure**: Event schemas define asynchronous message payloads only and must NOT import Kafka client code, producers, consumers, or database models.
2. **Decoupled from API Contracts**: API contracts represent synchronous HTTP REST communication. Event contracts represent asynchronous event stream messages.
3. **Explicit Versioning**: Every event schema must include a version property (e.g., `eventVersion: 1`).
4. **Idempotency Support**: Event payloads must include unique identifiers (`eventId`) and correlation keys (`correlationId`) to allow consumers to safely handle duplicate message deliveries.
