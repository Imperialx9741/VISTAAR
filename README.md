# VISTAAR

VISTAAR is an India-only ride-hailing platform with three applications in this repository:

- **`apps/backend`** — a FastAPI/Python REST API: identity & OTP auth, ride matching, driver/vehicle verification, wallet, pricing, admin RBAC, safety/SOS, support, promotions, referrals, notifications, advertisements, reporting, and monitoring.
- **`apps/mobile`** — one unified Flutter app for both roles ("User"/customer and "Sarthi"/driver, chosen at login — see [ADR-0027](docs/14-decisions/ADR-0027-unified-mobile-app-role-based-login.md)).
- **`apps/admin-web`** — a Next.js operations console for VISTAAR staff (Super Admin + employee admins with per-module VIEW/MANAGE permissions).

The ride fare itself is paid customer-to-driver directly (cash/UPI) — VISTAAR never collects it. What VISTAAR *does* collect is a per-ride platform fee from the driver's own wallet ([ADR-0025](docs/14-decisions/), [ADR-0060](docs/14-decisions/ADR-0060-sarthi-wallet-recharge-razorpay-test-gateway.md)).

**Project status**: paused as of 2026-09-09. Read **[`docs/VISTAAR_STATUS.md`](docs/VISTAAR_STATUS.md) Part 7 first** if you're resuming after a break — it's the authoritative "what's actually done, what's genuinely open" record, verified against real code, not against any document's own completion claims.

---

## Quick Start (experienced developers)

Assumes every prerequisite in [§2](#2-prerequisites--fresh-windows-pc) is already installed.

```powershell
# 1. Clone and inspect
git clone <REPOSITORY_URL> VISTAAR
cd VISTAAR
git status
type docs\VISTAAR_STATUS.md | more

# 2. Configure local secrets (see §5 — copy each .example, fill in real values)
copy .env.example .env
copy apps\mobile\dart_define.example.json apps\mobile\dart_define.json
copy apps\admin-web\.env.local.example apps\admin-web\.env.local

# 3. Start local infrastructure (Postgres/Redis/Kafka/monitoring)
docker compose -f infrastructure/docker/docker-compose.dev.yml up -d

# 4. Backend — new terminal
cd apps\backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
uvicorn src.main:app --reload --host 0.0.0.0    # 0.0.0.0 if a phone needs to reach it
curl http://127.0.0.1:8000/health               # expect {"status":"OK"}

# 5. Admin Web — new terminal
cd apps\admin-web
npm install
npm run dev                                      # http://localhost:3000

# 6. Mobile — new terminal, once dart_define.json's API_BASE_URL matches your LAN IP
cd apps\mobile
flutter pub get
flutter run --dart-define-from-file=dart_define.json

# 7. Run the tests (see §17 for the full breakdown)
cd apps\backend  && pytest
cd apps\mobile   && flutter test
cd apps\admin-web && npm test
```

---

## Table of Contents

1. [Complete Technology Stack](#1-complete-technology-stack)
2. [Prerequisites — Fresh Windows PC](#2-prerequisites--fresh-windows-pc)
3. [Exact Development Environment](#3-exact-development-environment)
4. [Clone the Project](#4-clone-the-project)
5. [Environment Configuration](#5-environment-configuration)
6. [External Accounts and Credentials](#6-external-accounts-and-credentials)
7. [First-Time Local Infrastructure Setup](#7-first-time-local-infrastructure-setup)
8. [Database Setup](#8-database-setup)
9. [Backend — Exact Startup Procedure](#9-backend--exact-startup-procedure)
10. [Admin Web — Exact Startup Procedure](#10-admin-web--exact-startup-procedure)
11. [Mobile — Exact Startup Procedure](#11-mobile--exact-startup-procedure)
12. [Mobile Configuration](#12-mobile-configuration)
13. [Firebase Setup](#13-firebase-setup)
14. [MapTiler Setup](#14-maptiler-setup)
15. [Razorpay Setup](#15-razorpay-setup)
16. [Sentry Setup](#16-sentry-setup)
17. [Testing — Exact Commands](#17-testing--exact-commands)
18. [Build Commands](#18-build-commands)
19. [Docker](#19-docker)
20. [AWS Deployment](#20-aws-deployment)
21. [AWS Terraform](#21-aws-terraform)
22. [Production Secrets](#22-production-secrets)
23. [Common Errors / Troubleshooting](#23-common-errors--troubleshooting)
24. [Development Workflow](#24-development-workflow)
25. [How to Resume VISTAAR Months Later](#25-how-to-resume-vistaar-months-later)
26. [Architecture Diagram](#26-architecture-diagram)
27. [Developer Checklist](#27-developer-checklist)

---

## 1. Complete Technology Stack

Every version below is read directly from this repository's own lockfiles/manifests — not assumed. Where a real repo file only sets a *floor* (`>=`) rather than an exact pin, that's stated explicitly.

### Mobile (`apps/mobile`)

| Category | Technology | Version | Purpose | Required locally? |
|---|---|---|---|---|
| Language/SDK | Dart | `^3.13.0` (pinned floor, `pubspec.yaml`) | App language | Yes |
| Framework | Flutter | Not pinned in this repo — CI (`ci.yml`) uses the `stable` channel, whatever that resolves to at run time | App framework | Yes |
| Android | Android Gradle Plugin | `9.1.0` | Android build | Yes (Android builds) |
| Android | Kotlin | `2.4.0` | Android glue code | Yes (Android builds) |
| Android | `com.google.gms.google-services` | `4.3.15` | Reads `google-services.json` for Firebase | Yes (Android builds) |
| Android | `compileSdk` | `37` | Compile-time Android API surface | Yes (Android builds) |
| Android | `minSdk`/`targetSdk` | Flutter's own bundled default (not overridden in this repo — verify with `flutter doctor`/a real build) | Install/runtime API level | Yes (Android builds) |
| Android | Java | `17` (`sourceCompatibility`/`targetCompatibility`, `kotlin.jvmTarget`) | Android toolchain | Yes (Android builds) |
| State | `provider` | `^6.1.2` | Session/auth state | — |
| Networking | `http` | `^1.2.0` | Backend API calls | — |
| Storage | `flutter_secure_storage` | `^11.0.0` | Persisted session (keychain/keystore) | — |
| Location | `geolocator` | `^14.0.0` | Device position | — |
| Maps | `flutter_map` + `latlong2` | `^8.2.2` / `^0.9.1` | Map rendering against MapTiler tiles | — |
| Push | `firebase_core` / `firebase_messaging` | `^4.14.0` / `^16.6.0` | FCM push notifications | — |
| Payments | `razorpay_flutter` | `^1.4.0` | Sarthi wallet recharge (TEST mode) | — |
| Contacts | `flutter_contacts` | `^2.3.1` | "Book for someone else" native picker | — |
| Media | `image_picker` | `^1.1.2` | Document/evidence camera-gallery capture | — |
| Typography | `google_fonts` | `^6.2.1` | Sora/Manrope brand fonts | — |
| Errors | `sentry_flutter` | `^9.0.0` (resolves to `9.29.0` as installed) | Crash/error reporting | — |
| Dev | `flutter_lints` | `^6.0.0` | Static analysis rules | Dev only |
| Dev | `flutter_launcher_icons` | `^0.14.3` | Generates the launcher icon from `assets/icon/` | Dev only, one-shot |

### Admin Web (`apps/admin-web`)

| Category | Technology | Version | Purpose | Required locally? |
|---|---|---|---|---|
| Runtime | Node.js | Not pinned by an `engines` field in `package.json` — CI (`ci.yml`) uses **Node 20**, the closest thing to an authoritative version | JS runtime | Yes |
| Package manager | npm | Whatever ships with the Node install above (`package-lock.json` present — use `npm`, not `pnpm`/`yarn`) | Dependency install | Yes |
| Framework | Next.js | `16.3.1` (exact pin) | App Router, SSR | Yes |
| ⚠ | | | **This is a pre-release/very-new Next.js with real breaking changes from what you may know.** `apps/admin-web/AGENTS.md` — read before touching any admin-web code — says to consult `node_modules/next/dist/docs/` for this exact version's conventions, not assumed prior knowledge. | |
| UI | React / React DOM | `19.2.8` (exact pin) | UI library | Yes |
| Language | TypeScript | `^5` (floor only, not exact-pinned) | Type checking | Yes |
| Lint | ESLint + `eslint-config-next` | `^9` / `16.3.1` | Linting | Dev only |
| Test | Vitest | `^3.2.7` | Unit/component tests | Dev only |
| Test | `@testing-library/react` + `jest-dom` + `user-event` | `^16.3.3` / `^6.9.1` / `^14.6.6` | Component test helpers | Dev only |
| Test env | `jsdom` | `^25.0.1` | DOM simulation for Vitest | Dev only |
| Errors | `@sentry/nextjs` | `^10.73.0` | Crash/error reporting | — |

### Backend (`apps/backend`)

| Category | Technology | Version | Purpose | Required locally? |
|---|---|---|---|---|
| Language | Python | `>=3.12` (`pyproject.toml`) — **do not use 3.15 alpha/pre-release** (see [§23](#23-common-errors--troubleshooting)) | Backend language | Yes |
| Web framework | FastAPI | `>=0.110.0` | HTTP API | Yes |
| ASGI server | Uvicorn | `>=0.28.0` | Runs FastAPI | Yes |
| Validation | Pydantic | `>=2.6.0` | Request/response schemas | Yes |
| ORM | SQLAlchemy | `>=2.0.0` | Database access | Yes |
| Migrations | Alembic | `>=1.13.0` | Schema migrations | Yes |
| DB driver | `psycopg2-binary` | `>=2.9.9` | PostgreSQL driver | Yes |
| Cache/queue client | `redis` | `>=5.0.0` | Redis client | Yes |
| Streaming | `aiokafka` | `>=0.10.0` | Kafka producer/consumer | Yes |
| Auth | `pyjwt[crypto]` | `>=2.8.0` | Access/refresh tokens; `[crypto]` for FCM's RS256 service-account JWT | Yes |
| Object storage | `boto3` | `>=1.34.0` | S3 (or S3-compatible) presigned uploads | Yes |
| HTTP client | `httpx` | `>=0.27.0` | MSG91 SMS calls (runtime, not just tests) | Yes |
| Background jobs | `celery[redis]` | `>=5.4.0` | Scheduled tasks (Beat + worker) | Only if running the worker |
| MFA | `pyotp` | `>=2.9.0` | Admin TOTP (RFC 6238) | Yes |
| Errors | `sentry-sdk[fastapi]` | `>=2.0.0` | Crash/error reporting | — |
| Metrics | `prometheus-fastapi-instrumentator` | `>=7.0.0` | Exposes `GET /metrics` | Yes |
| Uploads | `python-multipart` | `>=0.0.9` | CSV bulk-targeting multipart parsing | Yes |
| Config | `python-dotenv` | `>=1.0.0` | Loads repo-root `.env` on plain `uvicorn` runs | Yes |
| Dev — tests | `pytest` | `>=8.0.0` | Test runner | Dev only |
| Dev — lint/format | `ruff` | `>=0.3.0` | Format + lint | Dev only |
| Dev — types | `mypy` | `>=1.9.0` | Static type checking | Dev only |
| Lockfile | `uv` + `uv.lock` | `uv==0.9.*` (Dockerfile) | Reproducible **production image** builds only — plain local dev doesn't need `uv` | Docker/CI only |

### Database

| Technology | Version | Purpose |
|---|---|---|
| PostgreSQL | 16 (`postgis/postgis:16-3.4` image) | Primary relational database |
| PostGIS | bundled in the `16-3.4` image | `GEOMETRY(Point, 4326)` columns (`ride.rides` pickup/destination) |

### Infrastructure & local services (`infrastructure/docker/docker-compose.dev.yml`)

| Service | Image | Local port |
|---|---|---|
| PostgreSQL/PostGIS | `postgis/postgis:16-3.4` | `5433` → container `5432` |
| Redis | `redis:7-alpine` | `6379` |
| Kafka (KRaft mode) | `apache/kafka:3.7.0` | `9092` |
| Prometheus | `prom/prometheus:v2.53.0` | `9090` |
| Alertmanager | `prom/alertmanager:v0.27.0` | `9093` |
| Grafana | `grafana/grafana:11.1.0` | `3001` → container `3000` |

The backend itself is **not** a compose service — it runs directly via `uvicorn` on the host and reaches these containers by their published ports (Prometheus reaches the host backend the other direction, via `host.docker.internal`).

### Deployment infrastructure (see [§20](#20-aws-deployment)/[§21](#21-aws-terraform))

| Technology | Version | Purpose |
|---|---|---|
| Docker | Desktop, any recent version | Local containers + production image builds |
| Terraform | `>=1.7.0` (`required_version`, `infrastructure/terraform/aws/versions.tf`) | AWS infrastructure as code |
| `hashicorp/aws` provider | `~>5.60` | AWS resources |
| `cyrilgdn/postgresql` provider | `~>1.21` | Enables the PostGIS extension on RDS |
| `hashicorp/tls` provider | `~>4.0` | EKS OIDC provider certificate |
| kubectl | matching your EKS cluster's minor version | Applying `infrastructure/kubernetes/` manifests |
| AWS CLI | any recent v2 | Auth/credentials for Terraform + kubectl |

### External services actually integrated

| Service | Used for |
|---|---|
| MSG91 | OTP SMS (`SMS_PROVIDER=msg91`) — `dev` (console-log) is the default |
| Firebase / FCM | Push notifications (mobile) |
| MapTiler Cloud | Map tile rendering (mobile) |
| Razorpay | Sarthi wallet-recharge **TEST-mode** gateway only — never the ride fare |
| Sentry | Error tracking — **three separate projects**, one per app |
| Slack | Alertmanager alert delivery (incoming webhook) |
| AWS S3 | Document/evidence object storage |

**Not yet integrated** (checked directly, not assumed): a real payment gateway for anything beyond wallet recharge, WhatsApp Business (BSP unselected), an LLM provider for AI Support, VAHAN/SARATHI government vehicle-verification APIs, Google Play Console, Apple Developer Program (iOS has never been built once in this project — see `apps/mobile/README.md`'s own "Known gaps").

---

## 2. Prerequisites — Fresh Windows PC

Install only what you need for the parts of VISTAAR you're working on — the table notes which.

| Software | Version | Why needed | Official install | Verify |
|---|---|---|---|---|
| Git | any recent | Clone/version this repo | [git-scm.com](https://git-scm.com/) | `git --version` |
| Python | **3.12.x** — not 3.15 alpha (see §23) | Backend | [python.org](https://www.python.org/downloads/) or the `py` launcher | `py -3.12 --version` |
| Node.js | 20.x | Admin Web | [nodejs.org](https://nodejs.org/) | `node --version` |
| Flutter SDK | `stable` channel (see §1 — no exact pin) | Mobile | [docs.flutter.dev/get-started/install](https://docs.flutter.dev/get-started/install) | `flutter --version` |
| Android Studio | recent, with Android SDK + platform-tools | Android build tooling, emulator, device drivers | [developer.android.com/studio](https://developer.android.com/studio) | `flutter doctor` |
| A JDK | 17 (matches `apps/mobile/android`'s `sourceCompatibility`) | Android Gradle builds | usually bundled with Android Studio | `java -version` |
| Docker Desktop | any recent version with WSL2 backend on Windows | Local Postgres/Redis/Kafka/monitoring, and building the backend's production image | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) | `docker --version` |
| AWS CLI | v2 | AWS deployment work only | [aws.amazon.com/cli](https://aws.amazon.com/cli/) | `aws --version` |
| kubectl | v2, roughly matching your EKS minor version | AWS deployment work only | [kubernetes.io/docs/tasks/tools](https://kubernetes.io/docs/tasks/tools/) | `kubectl version --client` |
| Terraform | `>=1.7.0` | AWS deployment work only | [developer.hashicorp.com/terraform/install](https://developer.hashicorp.com/terraform/install) | `terraform version` |

Not needed for local development at all: `uv` (only the production Docker build and CI use it), `pnpm`/`yarn` (this repo uses npm, evidenced by `package-lock.json`), Helm (no Helm charts exist in this repo — plain `kubectl apply` against `infrastructure/kubernetes/`).

---

## 3. Exact Development Environment

VISTAAR is a monorepo with **four separate, independent dependency environments** — installing one does nothing for the others:

| Environment | Where | Isolated by | Install command |
|---|---|---|---|
| Root project | repo root | Nothing to install — this level only holds docs, `docker-compose`, Terraform, and shared config (`.env`, `.gitignore`) | — |
| Backend | `apps/backend` | A Python virtualenv (`apps/backend/.venv`) — **do not** `pip install` into your system/global Python | `py -3.12 -m venv .venv` then `pip install -e .[dev]` |
| Admin Web | `apps/admin-web` | `node_modules/`, resolved from `package-lock.json` | `npm install` |
| Mobile | `apps/mobile` | Flutter's own `.dart_tool/`/pub cache, plus a separate native Android/iOS toolchain per platform | `flutter pub get` |

**Shell**: every command in this README is written for **PowerShell** (Windows' default). A few backend commands work identically in Git Bash; where one genuinely differs, it's called out. Don't mix `cmd.exe` syntax in — it isn't used here.

**Do not assume file locations** — the three apps are siblings under `apps/`, not nested inside each other:
```
VISTAAR/
  apps/
    backend/     FastAPI, Python, apps/backend/.venv
    admin-web/   Next.js, Node, apps/admin-web/node_modules
    mobile/      Flutter, Dart
  docs/          ADRs, specs, VISTAAR_STATUS.md (the resume point)
  infrastructure/
    docker/      docker-compose.dev.yml + monitoring configs
    kubernetes/  plain K8s manifests (provider-agnostic)
    terraform/aws/   the current, active deployment IaC
    terraform/digitalocean/  superseded (ADR-0063) — kept for history only, not used
  .env.example, .gitignore
```

---

## 4. Clone the Project

```powershell
git clone <REPOSITORY_URL> VISTAAR
cd VISTAAR
git branch --show-current      # expect: main
git status                     # expect: clean
type README.md | more          # this file
type docs\VISTAAR_STATUS.md | more   # THE authoritative "what's actually done" record
```

No repository URL or access token is written here — use whatever your own Git hosting/SSH/token setup already provides; that's outside this file's scope on purpose (never put credentials in a README).

---

## 5. Environment Configuration

Three files hold real, local-only configuration. **None of the three is committed** (all covered by `.gitignore`/each app's own `.gitignore`) — each has a checked-in `.example`/`.local.example` sibling documenting every variable **name**, never a real value.

| File | Purpose | Who creates it | Where values come from |
|---|---|---|---|
| `.env` (repo root) | Backend runtime config — database/Redis/Kafka URLs, JWT secret, SMS/storage/push/payment/monitoring credentials, rate limits | You, from `.env.example` | See table below, per variable |
| `apps/mobile/dart_define.json` | Mobile compile-time config — backend URL, MapTiler key, Sentry DSN | You, from `dart_define.example.json` | Your LAN IP (backend URL) + real provider dashboards |
| `apps/admin-web/.env.local` | Admin Web runtime config — backend URL, Sentry DSN | You, from `.env.local.example` | Same sources as above |

**Never committed, by variable name** (real values must never appear in any commit, PR description, or this README):

`.env` — `DATABASE_URL` (if it embeds real prod credentials), `JWT_SECRET`, `STORAGE_ACCESS_KEY`/`STORAGE_SECRET_KEY`, `MSG91_AUTH_KEY`, `FCM_SERVICE_ACCOUNT_JSON` (a *path* — the JSON file itself must never be committed either), `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/`RAZORPAY_WEBHOOK_SECRET`, `SENTRY_DSN`, `ALERTMANAGER_SLACK_WEBHOOK_URL`.

`apps/mobile/dart_define.json` — `MAPTILER_API_KEY`, `SENTRY_DSN`.

`apps/admin-web/.env.local` — `NEXT_PUBLIC_SENTRY_DSN` (a Sentry DSN is designed to be public/client-embeddable, but still shouldn't be hand-copied into docs/chat unnecessarily).

**Local-only, non-secret, still needs setting every time your network changes**: `dart_define.json`'s `API_BASE_URL` and `.env`'s `DATABASE_URL` port — see [§9](#9-backend--exact-startup-procedure) and [§11](#11-mobile--exact-startup-procedure), both documented failure modes this project hit for real.

---

## 6. External Accounts and Credentials

| Service | Why VISTAAR uses it | Account required? | Test mode? | Production mode? | Configure where |
|---|---|---|---|---|---|
| MSG91 | OTP SMS delivery | Yes, for real SMS | `SMS_PROVIDER=dev` needs none (logs to console) | `SMS_PROVIDER=msg91` + `MSG91_AUTH_KEY`/`MSG91_TEMPLATE_ID` | `.env` |
| Firebase | Push notifications (FCM), one project for both mobile roles | Yes | Same Firebase project serves both — no separate test project evidenced | `firebase_options.dart` (client) + `FCM_SERVICE_ACCOUNT_JSON` (server) | See [§13](#13-firebase-setup) |
| MapTiler Cloud | Map tile rendering | Yes | The one API key is used for both — MapTiler doesn't split test/prod by default | Same key | `dart_define.json` |
| Razorpay | Sarthi wallet-recharge gateway only | Yes | `WALLET_RECHARGE_PROVIDER=dev` needs none; TEST mode needs a real Razorpay TEST account | **Not configured in this repo** — ADR-0060 §5 names SBI as the planned production gateway, not Razorpay | `.env` |
| Sentry | Error tracking — 3 separate projects (backend, mobile, admin-web) under one org | Yes | N/A — same DSN either way; empty DSN = disabled | Same | `.env` / `dart_define.json` / `.env.local` |
| Slack | Alertmanager alert delivery | Yes (workspace + incoming webhook) | N/A | Same webhook | `.env` (`ALERTMANAGER_SLACK_WEBHOOK_URL`) |
| AWS | S3 storage now; RDS/ElastiCache/EKS/ECR for deployment ([§20](#20-aws-deployment)) | Yes | `STORAGE_ENDPOINT` blank = real S3; point it at a local MinIO to avoid a real account for pure local dev | Real AWS account + IAM | `.env` (app), AWS CLI/Terraform (infra) |
| Google Play Console | Android release distribution | **Not yet set up** — no evidence in this repo | — | — | N/A yet |
| Apple Developer Program | iOS builds/distribution | **Not yet set up** — iOS has never been built once in this project (`apps/mobile/README.md`) | — | — | N/A yet |
| VAHAN/SARATHI (Govt. of India) | Vehicle/license verification | **Not yet integrated** — flagged as a real, undecided external dependency (`docs/VISTAAR_STATUS.md` Part 5) | — | — | N/A yet |

---

## 7. First-Time Local Infrastructure Setup

Real commands, from `infrastructure/docker/docker-compose.dev.yml`:

```powershell
# 1. Start Docker Desktop (GUI, or `wsl` if you run it headless)

# 2-4. Start Postgres, Redis, Kafka, Prometheus, Alertmanager, Grafana — one command
docker compose -f infrastructure/docker/docker-compose.dev.yml up -d

# 5. Verify containers are healthy
docker compose -f infrastructure/docker/docker-compose.dev.yml ps

# 6. Run database migrations (from apps/backend, venv active)
cd apps\backend
alembic upgrade head

# 7. Verify database health (once the backend is also running — see §9)
curl http://127.0.0.1:8000/health/db
curl http://127.0.0.1:8000/health/redis
curl http://127.0.0.1:8000/health/kafka
```

---

## 8. Database Setup

| | |
|---|---|
| Engine | PostgreSQL 16 + PostGIS (`postgis/postgis:16-3.4`) |
| Development database | `vistaar_db` |
| Test database | `vistaar_test_db` — created automatically by the test suite, never by you |
| User | `db_user` / `db_password` (local dev only — real production credentials come from AWS Secrets Manager, [§22](#22-production-secrets)) |
| Port | **`5433`** on the host (mapped from the container's `5432` — deliberately not `5432`, to avoid colliding with any other local Postgres install) |
| Migrations | Alembic, run from `apps/backend/` |

### ⚠ `vistaar_db` vs `vistaar_test_db` — read this before running anything

**`vistaar_db` is the real development database** — the one `uvicorn`, the Admin Web, and the mobile app all read and write to during manual testing. **`vistaar_test_db` is a fully isolated database that `pytest` alone uses.**

`apps/backend/tests/conftest.py` forces every test run onto `vistaar_test_db` before any test module even imports `core.config` — this is why running `pytest` never needs `vistaar_db` to exist or be migrated first.

**This wasn't always true.** `tests/_integration_db.py`'s own docstring documents a real historical bug: before this isolation existed, every DB-backed test ran directly against `vistaar_db`, and the resulting pollution (~1,800 rows from two test runs on 2026-08-21/22) sat in the development database for weeks before being found and cleaned up (2026-09-08). The isolation fix above prevents `pytest` from ever doing this again — but a one-off diagnostic script that imports `core.database.SessionLocal()` directly (not through `pytest`) still talks to the real `vistaar_db`, with no automatic cleanup. See `apps/backend/README.md` §5 ("Manual diagnostic scripts and the dev database") for the convention to follow if you ever need to run one.

Alembic commands (from `apps/backend/`):
```powershell
alembic current                                  # check current migration state
alembic revision --autogenerate -m "description"  # generate a new migration
alembic upgrade head                              # apply migrations
alembic downgrade -1                               # revert one migration
```

---

## 9. Backend — Exact Startup Procedure

```powershell
# 1. Open PowerShell, navigate to the backend
cd apps\backend

# 2. Activate the virtual environment (create it first if you haven't — §2/§3)
.venv\Scripts\Activate.ps1

# 3. Ensure Docker infrastructure is running (§7)
docker compose -f ..\..\infrastructure\docker\docker-compose.dev.yml ps

# 4. Ensure .env exists at the repo root (§5) — the backend loads it automatically
#    (python-dotenv, added 2026-09-08; walks up from apps/backend/src/core/config.py
#    to find it regardless of your current directory)

# 5. Run migrations if the schema has changed since you last pulled (§8)
alembic upgrade head

# 6. Start Uvicorn
uvicorn src.main:app --reload --host 0.0.0.0
```

**`127.0.0.1` vs `0.0.0.0`** — this matters and this project hit it for real:
- `uvicorn src.main:app --reload` with **no `--host` flag defaults to `127.0.0.1`** — only this same machine can reach it. Fine for Admin Web dev on the same laptop.
- **A physical Android device (or any other machine on your network) can never reach a `127.0.0.1`-bound server**, no matter what IP you configure client-side — confirmed directly this project (`Get-NetTCPConnection` showed only a `127.0.0.1` listener; the backend's own LAN address was unreachable even from the same machine). Use **`--host 0.0.0.0`** to bind every interface, including Wi-Fi, whenever mobile testing on a real device is involved.

Health check: `http://127.0.0.1:8000/health` → `{"status":"OK"}`. Swagger docs: `http://127.0.0.1:8000/docs`.

**For physical Android testing**, `apps/mobile/dart_define.json`'s `API_BASE_URL` must be your host PC's **current LAN IP** (`Get-NetIPAddress` / `ipconfig`), not `127.0.0.1` and not `10.0.2.2` (that address is the Android *emulator's* special alias for the host, not valid for a real device). This IP changes on Wi-Fi reconnects — see [§23](#23-common-errors--troubleshooting).

---

## 10. Admin Web — Exact Startup Procedure

```powershell
cd apps\admin-web
npm install
npm run dev
```

Opens at `http://localhost:3000`.

**Admin authentication**: there is no self-service sign-up. The *first* Super Admin must be provisioned directly against the database, from `apps/backend` with the venv active:
```powershell
python scripts\provision_admin.py --phone +91XXXXXXXXXX --role super_admin
```
No credential is generated by this script — that account then signs in the normal way, phone + OTP, at `http://localhost:3000/login`. Once one Super Admin exists, they can create employee admins from the Admin Management screen in the UI — the script is only for bootstrapping the very first account.

**Verifying the Dashboard shows real data, not sample data**: there is no sample-data fallback anymore (removed 2026-09-08) — every page either shows real data from the backend or a real error state. If you see a number that looks suspiciously like a round demo value (e.g. exactly `18,650`), that's a sign something regressed, not expected behavior; check the browser Network tab for the actual API response.

---

## 11. Mobile — Exact Startup Procedure

```powershell
# 1. Connect an Android phone via USB, or start an emulator from Android Studio.
# 2. On the phone: Settings → About phone → tap "Build number" 7 times (enables Developer Options).
# 3. Settings → Developer Options → enable USB debugging.
# 4. Verify ADB sees the device:
adb devices
# 5. Verify Flutter sees it too:
flutter devices
# 6. Check backend reachability BEFORE running the app —
#    from the SAME network the phone is on, not just this PC's own loopback:
curl http://<your-LAN-IP>:8000/health
# 7. Configure API_BASE_URL (see §12) to that same LAN IP.
# 8. Get Flutter dependencies:
flutter pub get
# 9. Run:
flutter run --dart-define-from-file=dart_define.json -d <device-id-from-flutter-devices>
```

**Physical-device requirements**:
- Phone and laptop must be on the **same Wi-Fi network** for a LAN-IP backend to be reachable at all.
- The backend must be bound with `--host 0.0.0.0` ([§9](#9-backend--exact-startup-procedure)) — a `127.0.0.1`-only backend is invisible to the phone regardless of IP configuration.
- Windows Firewall can separately block inbound connections to port 8000 from other LAN devices even once the backend is correctly bound — not yet verified as an issue in this project, but the next thing to check if connectivity still fails after the above two are confirmed correct.

**Why `127.0.0.1` doesn't mean "the laptop" from the phone's perspective**: `127.0.0.1` is the *loopback* address — on the phone, it means the phone itself, not your laptop. There is no way to reach your laptop from a physical device using `127.0.0.1`; you must use the laptop's real network address.

---

## 12. Mobile Configuration

`apps/mobile/dart_define.json` (gitignored — copy from `dart_define.example.json`):

| Variable | Purpose | Dev/test value | Production value |
|---|---|---|---|
| `API_BASE_URL` | Backend base URL | Your laptop's current LAN IP, e.g. `http://192.168.1.5:8000` | The real deployed backend's URL |
| `MAPTILER_API_KEY` | Map tile rendering | A real MapTiler Cloud key (empty is supported — maps degrade to a notice, not a crash) | Same key, or a production-tier one |
| `SENTRY_DSN` | Error tracking | This app's own Sentry project DSN (empty disables Sentry entirely) | Same or a separate prod project |

All three are **compile-time constants** (`String.fromEnvironment`) — changing this file requires a fresh `flutter run`/build, **not** a hot reload.

Firebase configuration (`google-services.json`, `firebase_options.dart`) is separate — see [§13](#13-firebase-setup).

---

## 13. Firebase Setup

One Firebase project ("VISTAAR Production") serves **both** mobile roles — there is no separate per-role Firebase app.

### Client (mobile app)
- `apps/mobile/lib/firebase_options.dart` — generated by the **FlutterFire CLI** (`flutterfire configure`), gitignored, never committed.
- `apps/mobile/android/app/google-services.json` — downloaded from the Firebase Console, read by the `com.google.gms.google-services` Gradle plugin. **Android is fully configured in this project.**
- **iOS is not configured** — no `GoogleService-Info.plist`, no Xcode "Push Notifications" capability enabled, no APNs Authentication Key uploaded. iOS has never been built once in this project (needs a real Mac + Xcode + Apple Developer access, none of which exist in the environment this was built in).

### Server (backend Admin credentials)
- `FCM_SERVICE_ACCOUNT_JSON` (`.env`) — a **file path** to a Firebase service-account JSON key, used to obtain an OAuth2 access token (RS256-signed JWT) for FCM's v1 HTTP API. The JSON file itself must live outside the repo (or in a path covered by `.gitignore`) and must **never** be committed.
- `PUSH_PROVIDER=dev` (default) logs pushes to console instead of calling FCM — no credential needed for that mode.

**Client Firebase config (public app identifiers) vs. server Admin credentials (a real service-account private key) are two completely different trust levels** — the former ships inside the compiled app, the latter must never leave the server.

---

## 14. MapTiler Setup

- Create an account at [maptiler.com](https://www.maptiler.com/), generate an API key.
- Set it as `MAPTILER_API_KEY` in `apps/mobile/dart_define.json`.
- Read by `AppConfig.mapTilerApiKey`/`hasMapTilerApiKey` (`lib/core/config/app_config.dart`); every map-touching screen must degrade to a plain notice, not crash, when no key is configured — this is a real, tested behavior, not a hope.

**What's actually implemented vs. not**, verified directly against the mobile source:
- **Map rendering** — real, via `flutter_map` + MapTiler raster tiles. Pickup/destination picking and a static route preview both work.
- **Live driver-location tracking on the map** — **not implemented**. No `/tracking` endpoint exists anywhere in the backend (verified by grepping the whole backend source) — this is a backend gap, not a MapTiler or mobile-side one.
- **Geocoding** (address ↔ coordinates) — **not evidenced as used**; the app collects raw latitude/longitude, not searched addresses.
- **Road-distance/fare calculation** — fares use a straight-line (haversine) distance, not a real routing/road-distance API call.

---

## 15. Razorpay Setup

Razorpay is used for **exactly one thing**: a Sarthi (driver) topping up their own platform-fee wallet. It is **not** the ride-fare payment gateway (VISTAAR never collects ride fare directly).

| | |
|---|---|
| Mode | **TEST only** in this repo — production is planned to be SBI instead ([ADR-0060](docs/14-decisions/ADR-0060-sarthi-wallet-recharge-razorpay-test-gateway.md) §5), not yet built |
| Webhook endpoint | `POST /api/v1/webhooks/wallet-recharge/razorpay` (verified directly against `modules/wallet/router.py`) |
| Event handled | `payment.captured` |
| Env variables | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` — three separate values (the webhook secret is distinct from the API key secret; get it from the Razorpay Dashboard → Webhooks, not the API Keys page) |
| Local testing limitation | Razorpay's webhook delivery requires a **publicly reachable HTTPS endpoint** — `localhost`/a LAN IP cannot receive it. Use a tunneling tool (ngrok or similar) pointed at your local backend to test the webhook path locally, or test the rest of the flow without triggering a real webhook delivery. |
| Enable it | `WALLET_RECHARGE_PROVIDER=razorpay` in `.env` (default is `dev` — logs only, never actually verifies/credits) |

Never put real key values in this README, a commit, or a PR description — set them only in `.env` (local) or your production secret store ([§22](#22-production-secrets)).

---

## 16. Sentry Setup

Three **separate** Sentry projects, one per app, under one org — so a mobile crash and a backend 500 never land in the same feed:

| App | DSN variable | Where |
|---|---|---|
| Backend | `SENTRY_DSN` | `.env` |
| Mobile | `SENTRY_DSN` | `apps/mobile/dart_define.json` |
| Admin Web | `NEXT_PUBLIC_SENTRY_DSN` | `apps/admin-web/.env.local` |

An empty/unset DSN is each SDK's own documented "disabled" state — not an error, and the normal state for pure local dev.

- Backend traces/profiles sample at `0.1` (10%) by default — a cost/volume decision, not a technical constraint; adjust `SENTRY_TRACES_SAMPLE_RATE`/`SENTRY_PROFILES_SAMPLE_RATE` if you hold the real account and want to change it.
- Backend test runs (`pytest`) force `SENTRY_DSN=""` (`tests/conftest.py`) so the test suite never sends real events to your Sentry project.
- No source-map upload / build-time auth token is configured for admin-web or mobile — a real gap if you want de-minified stack traces in Sentry; not built.

---

## 17. Testing — Exact Commands

| App | Command | What it tests | Expected result (as of the last verified run) |
|---|---|---|---|
| Backend | `pytest` (from `apps/backend`, venv active) | Full unit + API + integration suite, against isolated `vistaar_test_db` | 1,459 passed |
| Backend | `ruff format --check src tests` | Formatting | No diffs |
| Backend | `ruff check src tests` | Lint | No issues |
| Backend | `mypy src tests` | Static types | No issues |
| Mobile | `flutter test` (from `apps/mobile`) | Unit + widget tests, mocked HTTP — no backend needed | 267 passed |
| Mobile | `flutter analyze` | Static analysis | No issues |
| Admin Web | `npm test` (from `apps/admin-web`) — runs `vitest run` | Component/unit tests | 55 files / 227 passed |
| Admin Web | `npm run lint` | ESLint | 0 errors (2 pre-existing, accepted warnings about `window.location.href` at the sign-in/out boundary — a deliberate choice, not an oversight) |
| Admin Web | `npx tsc --noEmit` | Type-check | No issues |
| Admin Web | `npm run build` | Production build | Succeeds |

**Test database isolation** (see [§8](#8-database-setup) for the full story): `pytest` always runs against `vistaar_test_db`, never `vistaar_db`, because `tests/conftest.py` overrides `DATABASE_URL` before any test module imports backend config. You never need to create or migrate `vistaar_test_db` yourself — the test suite bootstraps it on first run.

No Playwright/Cypress/E2E browser suite exists in this repo — "integration" testing for the backend means the pytest suite's own DB-backed integration tests (`test_*_integration.py`), not a separate tool.

---

## 18. Build Commands

| Target | Command | Notes |
|---|---|---|
| Android APK (debug) | `flutter build apk --debug` (from `apps/mobile`) | Uses the debug signing key automatically |
| Android APK (release) | `flutter build apk --release` | Uses real release signing if `apps/mobile/android/key.properties` exists (gitignored — see [ADR-0064](docs/14-decisions/ADR-0064-android-release-signing.md)/`docs/16-mobile/android-release-signing.md`); **silently falls back to the debug key if it doesn't**, so a release build without it still succeeds but isn't really release-signed |
| Android App Bundle | `flutter build appbundle --release` | For Play Store upload — Play Console itself is not yet set up (§6) |
| Admin Web production build | `npm run build` (from `apps/admin-web`) | `next build` — verified passing |
| Backend production image | `docker build -t vistaar-backend:latest .` (from `apps/backend`) | Multi-stage; see [§19](#19-docker) |

No iOS build command is documented here — iOS has never been built once in this project (§6/§13).

---

## 19. Docker

### Local infrastructure
```powershell
# Start everything (Postgres/Redis/Kafka/Prometheus/Alertmanager/Grafana)
docker compose -f infrastructure/docker/docker-compose.dev.yml up -d

# Stop (keeps volumes/data)
docker compose -f infrastructure/docker/docker-compose.dev.yml stop

# Stop and remove containers (keeps named volumes, so data survives)
docker compose -f infrastructure/docker/docker-compose.dev.yml down

# Inspect status
docker compose -f infrastructure/docker/docker-compose.dev.yml ps

# Logs for one service
docker compose -f infrastructure/docker/docker-compose.dev.yml logs -f postgres
```

Named volumes (survive `down`, not `down -v`): `vistaar_postgres_data`, `vistaar_redis_data`, `vistaar_kafka_data`, `vistaar_prometheus_data`, `vistaar_grafana_data`. Network: `vistaar_dev_network`.

### Backend production image (`apps/backend/Dockerfile`)
Multi-stage build: a `python:3.12-slim` builder stage installs only `[project.dependencies]` (not the dev group) via `uv sync --frozen` into `/opt/venv`; the runtime stage (also `python:3.12-slim`) copies that venv plus `src/`, runs as a non-root `vistaar` user, and has a built-in `HEALTHCHECK` against `/health`.

```powershell
cd apps\backend
docker build -t vistaar-backend:latest .

docker run -d --name vistaar-backend -p 8000:8000 `
  --network vistaar_dev_network `
  --env-file ..\..\.env `
  vistaar-backend:latest

curl http://127.0.0.1:8000/health   # {"status":"OK"}

docker stop vistaar-backend
docker rm vistaar-backend
```

`uv.lock` must be regenerated (`uv lock`, requires `uv` installed) and committed whenever `pyproject.toml`'s dependencies change — this Docker build fails loudly (`--frozen`) if the two have drifted, rather than silently re-resolving.

---

## 20. AWS Deployment

**AWS is the current, decided deployment target** ([ADR-0063](docs/14-decisions/ADR-0063-aws-deployment-baseline.md), 2026-09-03 — explicitly supersedes an earlier DigitalOcean decision, [ADR-0035](docs/14-decisions/ADR-0035-digitalocean-deployment-and-production-dockerfile.md)). `infrastructure/terraform/digitalocean/` still exists in this repo but is **superseded, kept only as history — do not use it**.

```
Internet
   |
   v
 AWS ALB  (ADR-0067 — AWS Load Balancer Controller, TLS via ACM)
   |
   v
 Amazon EKS  (Kubernetes)
   |
   +---- FastAPI backend Deployment (infrastructure/kubernetes/backend-deployment.yaml)
   +---- Celery worker Deployment
   +---- Prometheus / Alertmanager / Grafana
   |
   +---- Amazon RDS PostgreSQL + PostGIS
   +---- Amazon ElastiCache for Redis
   +---- Self-hosted Kafka on EC2 (no managed Kafka used, matching the earlier DO decision's own reasoning)
   +---- Amazon S3 (object storage)

Admin Web
   |
   v
 AWS Amplify  (ADR-0068)
   |
   v
 EKS backend (above)
```

| Component | Status |
|---|---|
| `apps/backend/Dockerfile` | IMPLEMENTED — provider-agnostic, needed no changes for the AWS switch |
| `infrastructure/kubernetes/*.yaml` | IMPLEMENTED — plain Kubernetes YAML, provider-agnostic |
| `infrastructure/terraform/aws/*.tf` | CONFIGURED, **NOT APPLIED** — written and syntax-validated, no real AWS account exists in the environment this was built in |
| `infrastructure/terraform/aws-state-backend/` | CONFIGURED, NOT APPLIED — provisions the S3 bucket + lock table the main module's remote state needs |
| ECR image push | NOT DONE — no real AWS account/credentials available |
| Real EKS cluster / RDS / ElastiCache | NOT DEPLOYED |
| Admin Web on Amplify | CONFIGURED (ADR-0068), NOT DEPLOYED |

**Do not claim this is deployed to production — it is not, as of this pause.** Everything above the "CONFIGURED, NOT APPLIED" line is genuinely real and verified (syntax-validated against real Terraform/Kubernetes schemas); everything below it needs a real AWS account before it means anything.

Deployment prerequisites once a real AWS account exists: AWS account + IAM permissions for EKS/RDS/ElastiCache/S3/ECR/VPC, AWS CLI configured, Terraform, kubectl, a domain, an ACM certificate for the ALB.

---

## 21. AWS Terraform

```
infrastructure/terraform/
  aws-state-backend/   bootstraps the S3 bucket + DynamoDB lock table
                        the main module's remote state needs (apply this FIRST, once)
  aws/                 the actual infrastructure — EKS, RDS, ElastiCache,
                        self-hosted Kafka EC2, S3, ECR, VPC
  digitalocean/         superseded (ADR-0063) — do not use
```

```powershell
# One-time: provision the remote-state backend itself
cd infrastructure\terraform\aws-state-backend
terraform init
terraform plan
terraform apply

# Main infrastructure — copy backend.hcl.example first, fill in the real
# bucket/table names the step above just created
cd ..\aws
copy backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

⚠ **`terraform destroy` deletes real cloud infrastructure, including RDS/ElastiCache data** — never run it without being certain, and never against a real production state without an explicit, separate decision to do so.

These commands are written from the actual `versions.tf`/directory structure in this repo — verify against the real files before running anything if this section's own age is in doubt (see [§25](#25-how-to-resume-vistaar-months-later)).

---

## 22. Production Secrets

| Environment | Mechanism | Never do this |
|---|---|---|
| Local dev | `.env` / `dart_define.json` / `.env.local` — all gitignored | Commit any of the three, hardcode a secret in source, or paste one into a README/PR/commit message |
| AWS/Kubernetes | Kubernetes `Secret` objects (`infrastructure/kubernetes/backend-secret.example.yaml`, `alertmanager-secret.example.yaml`, `grafana-secret.example.yaml` — copy, fill in, `kubectl apply`, **never commit the filled-in file**) | Put a service-account JSON, a private key, or a real credential value into any file under `infrastructure/kubernetes/*.yaml` that isn't already named `*.example.yaml` |
| CI (GitHub Actions) | `secrets.*` context (`GITHUB_TOKEN`, `GITLEAKS_LICENSE`) | Print a secret to CI logs |

Secret scanning already runs in CI (`gitleaks-action`, full git history of the diff, not just the working tree) and container image scanning runs too (Trivy, CRITICAL/HIGH, unfixed findings ignored) — see `.github/workflows/ci.yml`.

---

## 23. Common Errors / Troubleshooting

Every item below is a real issue this project actually hit, not a generic guess.

| Symptom | Cause | Fix |
|---|---|---|
| `adb` not recognized | Android SDK platform-tools not on `PATH` | Add `<Android SDK>\platform-tools` to your `PATH`, or use the full path Android Studio installed it to |
| Flutter doesn't detect the phone | USB debugging not enabled, or the device hasn't authorized this computer | Enable USB debugging (§11), check the phone for an "Allow USB debugging?" prompt |
| `127.0.0.1` doesn't work from the Android phone | Loopback means "the phone itself" from the phone's perspective, not your laptop | Use the laptop's real LAN IP (§9/§11) |
| Backend connection refused | Uvicorn isn't running, crashed, or is bound to `127.0.0.1` only | Check the process is actually up; if a phone/other device needs it, restart with `--host 0.0.0.0` (§9) |
| Admin Dashboard shows "Something went wrong loading the dashboard" | Backend isn't reachable — check it's running and bound correctly before assuming a code/data problem | `curl http://127.0.0.1:8000/health` first |
| `API_BASE_URL` was correct yesterday, not today | Your laptop's LAN IP drifted (Wi-Fi reconnect/DHCP renewal) — happened at least three times in this project's own history | `Get-NetIPAddress`/`ipconfig`, update `dart_define.json`, **rebuild** (compile-time constant, hot reload won't pick it up) |
| Razorpay webhook never fires locally | Razorpay requires a publicly reachable HTTPS endpoint; `localhost`/a LAN IP can't receive it | Use a tunneling tool (ngrok or similar), or accept this path is untestable purely locally |
| `psycopg2.OperationalError: password authentication failed` on a fresh setup | `DATABASE_URL` pointing at port `5432` instead of `5433` — this project's own `.env`/`.env.example` both had this exact stale value at different points | Confirm the port is `5433` (§8) |
| Tests seem to have created test-looking rows in `vistaar_db` | A one-off diagnostic script (not `pytest`) was run directly against `core.database.SessionLocal()` | `pytest` itself is always isolated (§8); a manual script isn't — see `apps/backend/README.md` §5 for the convention |
| Backend works from this laptop but not from another device on the network | Almost certainly the `127.0.0.1`-vs-`0.0.0.0` binding issue (§9), possibly compounded by Windows Firewall (not yet confirmed as an issue in this project — check it if `--host 0.0.0.0` alone doesn't fix it) | |
| `pip install`/importing on Python fails with an ABI/slot error | You're on a Python 3.15 alpha build, not 3.12 — this project hit exactly this with Pillow | `py -0p` to list installed Pythons, use `py -3.12` explicitly everywhere |
| Admin session keeps logging you out every ~30 minutes | Working as designed until 2026-09-08 (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30`, no refresh) — fixed since: auto-refresh on token expiry now exists (`apps/admin-web/src/lib/api/client.ts`) | If it's still happening, that's a real regression to investigate, not expected |

---

## 24. Development Workflow

The standing process for every completed piece of work in this project, going forward:

1. Pick one logical task — never combine unrelated work.
2. Inspect the existing implementation before writing anything new (this project has a strong "verify against real code, not docs' own claims" discipline — `docs/VISTAAR_STATUS.md`'s own header states this explicitly).
3. Implement.
4. Run the tests relevant to that task (§17) — not necessarily the whole monorepo's suite every time.
5. Review the changed files.
6. Confirm no unrelated changes are included in what you're about to commit.
7. Create **one** focused Git commit, scoped to that single task, with a clear message.
8. Report: commit hash, commit message, files/categories included, which tests passed, and whether anything else remains uncommitted.
9. **Never push automatically** — commits stay local until explicitly approved for push.
10. Only move to the next task once that commit exists and has been reported.

---

## 25. How to Resume VISTAAR Months Later

1. `git pull` (or clone fresh) and confirm you're on the right branch.
2. **Read this README top to bottom** — versions and commands may have drifted since; verify anything that looks off against the real repo files it claims to summarize (§29's own discipline: never trust a stale doc over real code).
3. Read **`docs/VISTAAR_STATUS.md`**, especially **Part 7 ("Project Paused Here")** — the authoritative record of what was done right before the pause and what's genuinely still open.
4. Skim any ADRs added since Part 7's date, under `docs/14-decisions/`.
5. Re-verify every prerequisite version (§2) — Flutter/Node/Python patch releases move fast; don't assume last time's install is still current or still compatible.
6. Recreate your local secrets — `.env`, `dart_define.json`, `.env.local` (§5) — none of these survive a `git pull`, all three need real values again.
7. Start Docker infrastructure (§7).
8. Run migrations (§8).
9. Start the backend (§9), Admin Web (§10), and mobile (§11), in that order.
10. Connect an Android device or start an emulator before touching mobile.
11. Run every health check (§9/§10) before assuming anything is broken.
12. Run the full test suite for each app (§17) — a clean baseline before you change anything.
13. Continue from `docs/VISTAAR_STATUS.md`'s own documented open items (Part 5 for what needs the owner's input, Part 7 for what's unresolved from the pause itself — most notably, backend process stability was **worked around, not fully root-caused**; re-verify it's actually stable before building anything new on top of it).

---

## 26. Architecture Diagram

```
                    User / Sarthi Mobile (Flutter, one app, two roles)
                              |
                              v
                          AWS ALB  (TLS via ACM)
                              |
                              v
                        Amazon EKS
                              |
        +---------------------+---------------------+
        |                     |                     |
   FastAPI Backend      Celery Worker         Prometheus/Grafana
        |                (scheduled tasks)     /Alertmanager
        |
        +---- Amazon RDS (PostgreSQL + PostGIS)
        +---- Amazon ElastiCache (Redis)
        +---- Self-hosted Kafka (EC2)
        +---- Amazon S3 (document/evidence storage)

   Admin Web (Next.js) ---- AWS Amplify ---- (same EKS backend above)

   External services the backend/mobile call directly:
     MSG91 (OTP SMS) · Firebase/FCM (push) · MapTiler (map tiles)
     Razorpay (wallet recharge, TEST mode) · Sentry x3 (errors) · Slack (alerts)
```

Only components with real, verified evidence in this repo are shown — no aspirational/planned-only pieces (e.g. AI Support, WhatsApp) are included.

---

## 27. Developer Checklist

- [ ] Git installed
- [ ] Python 3.12.x (not 3.15 alpha) installed and verified (`py -3.12 --version`)
- [ ] Node.js 20.x installed
- [ ] Flutter (`stable` channel) installed, `flutter doctor` clean
- [ ] Android Studio + SDK + a JDK 17 installed
- [ ] Docker Desktop installed and running
- [ ] `.env`, `dart_define.json`, `.env.local` all copied from their `.example` and filled in
- [ ] `docker compose -f infrastructure/docker/docker-compose.dev.yml up -d` running, all services healthy
- [ ] Alembic migrations applied (`alembic upgrade head`)
- [ ] Backend running (`uvicorn src.main:app --reload [--host 0.0.0.0]`), `/health` returns 200
- [ ] Admin Web running (`npm run dev`), loads at `localhost:3000`
- [ ] A Super Admin provisioned (`scripts/provision_admin.py`), sign-in works
- [ ] Android device connected (`adb devices`/`flutter devices` both show it) or emulator running
- [ ] `dart_define.json`'s `API_BASE_URL` matches your current LAN IP
- [ ] `/health`, `/health/db`, `/health/redis`, `/health/kafka` all return 200
- [ ] `pytest` passes (backend)
- [ ] `flutter test` passes (mobile)
- [ ] `npm test` passes (admin-web)
