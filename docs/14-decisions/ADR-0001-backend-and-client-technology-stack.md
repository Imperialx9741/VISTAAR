ADR-0001 — Backend and Client Technology Stack

Status: Accepted
Date recorded: 2026-08-20
Deciders: Recorded from repository evidence during documentation/architecture
reconciliation. No separate approval meeting record exists; this ADR
formalizes what the repository already demonstrates as the working stack.

1. Context

docs/03-architecture/technical-architecture.md v2.0 §6 ("Technology Stack")
specifies:

- Core backend: Go 1.21+
- BFF/API: Node.js + Fastify
- Customer app: Next.js PWA
- Driver app: Flutter

The actual repository (apps/, infrastructure/, .github/workflows/ci.yml) does
not match this for the backend and customer app:

- apps/backend/pyproject.toml defines a Python 3.12 / FastAPI / SQLAlchemy 2 /
  Alembic / aiokafka / redis-py application ("vistaar-backend"), with a full
  dev toolchain (pytest, ruff, mypy) and no Go or Node/Fastify service
  anywhere in the repository.
- apps/customer-mobile/pubspec.yaml defines a Flutter application
  ("customer_mobile"), structurally identical to apps/driver-mobile/ (same
  lib/core, lib/features, lib/shared layout) — not a Next.js PWA.
- apps/driver-mobile/pubspec.yaml defines a Flutter application, matching
  the architecture doc's driver-app choice.
- apps/admin-web/package.json defines a Next.js 16 / React 19 application —
  the architecture doc does not describe a separate admin-web app at all.
- .github/workflows/ci.yml enforces, on every push/PR: `ruff format --check`,
  `ruff check`, `mypy`, and `pytest` for apps/backend/; `flutter analyze` and
  `flutter test` for both apps/customer-mobile/ and apps/driver-mobile/; and
  `npm run lint` plus a production `next build` for apps/admin-web/. This is
  a fully configured, CI-enforced toolchain for all four apps, not a
  placeholder or scaffold left over from `create-next-app`/`flutter create`.
- infrastructure/docker/docker-compose.dev.yml provisions PostgreSQL, Redis,
  and Kafka for local development, matching the backend's actual dependency
  configuration (apps/backend/src/core/database.py, redis.py, kafka.py).
- docs/11-implementation/implementation-readiness.md §5 states "the exact
  programming framework can be selected during implementation without
  changing the domain boundaries," explicitly deferring the backend language
  choice to implementation — consistent with a deliberate later pivot away
  from the architecture doc's Go/Node baseline.
- docs/04-domain-design/domain-design.md §46 ("Open Decisions") separately
  lists "Whether Go and Node domains are split into separate deployables" as
  still open at the time domain design was written, again consistent with
  the Go/Node choice never having been locked in before implementation
  started.

No document in docs/14-decisions/ previously recorded a stack decision, and
no document anywhere describes a Python/FastAPI or Flutter-customer-app pivot
as approved. This ADR closes that gap by recording what the repository
already demonstrates as the adopted, working, CI-enforced stack.

2. Decision

The following is the adopted technology stack for VISTAAR, superseding
technical-architecture.md v2.0 §6 and §57 where they conflict:

- Backend: Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic (single backend
  application, not a separate Go core service plus Node/Fastify BFF).
- Customer Mobile: Flutter (not a Next.js PWA).
- Driver Mobile: Flutter (unchanged from the architecture doc).
- Admin Web: Next.js (not previously described in the architecture doc as a
  distinct application).
- Infrastructure: PostgreSQL, Redis, Kafka, Docker (unchanged from the
  architecture doc's data/eventing choices).

3. Consequences

- technical-architecture.md §6 (Technology Stack table) and §57 (Frontend
  Architecture — Customer) are updated by this reconciliation to reflect the
  above, with a pointer back to this ADR. See the "Migration From Technical
  Architecture v1.0" precedent in that document (§68) for the established
  pattern of recording superseded assumptions.
- The BFF-as-separate-service concept in technical-architecture.md §7
  ("Service Boundary") does not currently correspond to any deployable in
  the repository; apps/backend is a single FastAPI application. This ADR
  does not resolve whether a separate BFF will be introduced later — that
  remains an open implementation choice under
  docs/11-implementation/implementation-readiness.md §75 ("Implementation
  Rule for Technical Choices"), not a business-policy question.
- This ADR does not change any business requirement, fare rule, or domain
  boundary. It only reconciles the technology-stack documentation with the
  stack the repository has already built and CI-tested against.

4. Scope note

This ADR was produced as part of a documentation/architecture reconciliation
task and deliberately does not modify any source code, dependency, CI
workflow, or Docker configuration — it only records and documents the stack
that already exists.
