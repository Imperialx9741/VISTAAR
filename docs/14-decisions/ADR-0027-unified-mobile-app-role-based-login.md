ADR-0027 — Unified VISTAAR Mobile App: One App, Role-Based Login
(Customer / VISTAAR Rider)

Status: Accepted
Date recorded: 2026-08-26
Deciders: Project owner (explicit product decision, communicated
directly, not inferred).

1. Decision

VISTAAR ships ONE mobile application, not two. On first launch, the
user chooses a role at login:

- **Customer** — the passenger booking rides.
- **VISTAAR Rider** — the driver operating a vehicle. ("Rider" is the
  product-facing name for the driver persona in this single app; it is
  not a third account type — it maps to the existing `AccountType.
  DRIVER` the backend already implements.)

Both roles authenticate through the same existing OTP flow
(api-contracts.md §6-7, `POST /api/v1/auth/otp/request` with
`account_type: "CUSTOMER"` or `"DRIVER"`, then `POST /api/v1/auth/otp/
verify`) — no backend change is required; `identity.accounts.
account_type` already distinguishes the two, and every domain module
already authorizes by account type (`require_customer`/`require_driver`).
This ADR is a client/product-architecture decision only.

2. Context

`apps/customer-mobile/` and `apps/driver-mobile/` already existed as two
separate Flutter project skeletons (ADR-0001 recorded this as the
adopted stack: Flutter for both). Neither had any real feature code —
both were exactly `flutter create` output plus a placeholder home
screen reading "Initial Application Skeleton." technical-architecture.md
§3's diagram and §6's stack table describe them as two distinct client
applications hitting the same backend.

The project owner has now decided this should be one app instead, with
role selection happening at login rather than by installing a different
app. Since neither existing skeleton contained real work, this is
consolidated into a single new Flutter project (`apps/mobile/`) rather
than merging two partially-built codebases — there was nothing to merge.
`apps/customer-mobile/` and `apps/driver-mobile/` are removed.
`apps/admin-web/` (Next.js) is unaffected — admin has always been,
and remains, a separate application; this decision is scoped to the
customer/driver mobile experience only.

3. What changes

- `apps/mobile/` — new Flutter project (Android + iOS + Web targets),
  replacing `apps/customer-mobile/` and `apps/driver-mobile/`.
- `.github/workflows/ci.yml` — the two separate `customer-mobile-checks`/
  `driver-mobile-checks` jobs are replaced with one `mobile-checks` job
  pointed at `apps/mobile/`.
- `technical-architecture.md` §3 (High-Level Architecture diagram) and
  §6 (Technology Stack table) — "Driver app" / "Customer app" rows
  collapse into one "Mobile app (Customer + Driver)" row; the diagram's
  two separate client boxes collapse into one.
- Scope built under this ADR (see §4): role selection + phone/OTP login
  only — a real, working vertical slice through the existing backend
  auth API, not the full ride-booking/driver-operations UI. Everything
  past login (ride booking screens, driver go-online/offer screens,
  etc.) is future work, out of this ADR's scope.

4. What this ADR does NOT do

- Does not change any backend code, API contract, or account-type model
  — `AccountType.CUSTOMER`/`AccountType.DRIVER` already exist and
  already work exactly as this app needs.
- Does not merge any actual feature code — there was none in either
  prior skeleton to merge.
- Does not build ride-booking, driver-availability, wallet, or any
  other post-login screen. Login (role selection → phone entry → OTP
  request → OTP verify → authenticated session) is the complete scope
  of the first implementation pass under this ADR.
- Does not change `apps/admin-web/` in any way.
- Does not select a state-management library, design system, or
  navigation package beyond what's needed for the login flow — those
  remain open choices for whoever builds the next screen, informed by
  what this first slice already uses (see the app's own README).

5. Consequences

VISTAAR now has three client applications instead of four: the unified
mobile app (`apps/mobile/`), Admin Web (`apps/admin-web/`), and the
FastAPI backend (`apps/backend/`) they both call. CI simplifies from
four jobs to three. Any future documentation or planning that assumed
"Driver App" and "Customer App" as separate installable products should
be read as "the Driver role" / "the Customer role" within the one
mobile app instead.
