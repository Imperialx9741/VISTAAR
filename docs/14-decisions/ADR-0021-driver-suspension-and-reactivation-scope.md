ADR-0021 — Driver Suspension & Reactivation: Scope and Open Items

Status: Accepted
Date recorded: 2026-08-24
Deciders: Approved under the owner's phase-level autonomy grant ("continue"
after Pricing Foundation, VISTAAR session, 2026-08-24) — the roadmap's own
mandatory stop conditions (§0.3) were checked and correctly do bite for
one part of this task's originally-assumed scope (see Decision 2).

1. Context

docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md scheduled this task as "Phase
03's driver suspension/reactivation — small, independent... pure
engineering, no external dependency (adds a SUSPENDED operational_status
value + admin action)." That assessment undersold the actual gap: the
SUSPENDED value already exists in `DriverOperationalStatus`
(domain-design.md §7.3), and `SuspendDriver`/`ReactivateDriver` are
already-documented commands (§7.4) — genuinely nothing new to design
there. But unlike `ApproveDriver`/`RejectDriver` (which had a real,
documented `POST /api/v1/admin/drivers/{id}/approve|reject` endpoint to
implement against from Task 2.7A), api-contracts.md documents **no**
HTTP endpoint anywhere for suspend or reactivate — the same
"domain/service layer real, HTTP surface genuinely absent" gap ADR-0018
hit for Advertisement, discovered only once building started, the same
class of correction this session has now made three times (Admin MFA,
Advertisement, this).

2. Decision 1 — Build the full domain/service layer; no schema change
   needed

`driver.drivers.operational_status` is a plain `VARCHAR(30)` with no
CHECK constraint (database-design.md §7.1) — `SUSPENDED` was always a
legal value at the database level, just never written by any code path.
`DriverService.suspend_driver()`/`reactivate_driver()` are added using
the exact concurrency-safe pattern `go_online()`/`go_offline()` already
established (`get_by_id_for_update()` row lock before any check or
write) — no migration, no new port method (`save()` already persists
arbitrary field changes).

3. Decision 2 — No HTTP endpoint is added; this is the §0.3 stop
   condition that actually bites

No `POST /api/v1/admin/drivers/{id}/suspend` (or `/reactivate`) request/
response shape, path, or error-code mapping is documented anywhere in
api-contracts.md — unlike Approve/Reject Driver, which had one already.
Inventing one now would be exactly the "new public API contract" gate
ADR-0018 already flagged for Advertisement. `suspend_driver()`/
`reactivate_driver()` are proven directly by unit tests (fake
repository) and a real-Postgres integration test exercising the full
lifecycle and a real concurrency test on the row lock — the same "prove
the composition without inventing a live call site" treatment ADR-0018
gave Advertisement's wallet-credit composition, and ADR-0019/0020 gave
Promotion's reserve/consume/restore before a caller existed for them.

4. Decision 3 — `suspend_driver()` accepts a `reason`, matching
   `reject_driver()`'s exact shape, even with no caller to pass one yet

`reject_driver(*, driver_id, reason: str | None)` already exists
(Task 2.7A) with `reason` not stored on `driver.drivers` (no such
column is documented) — the caller (`modules/admin/router.py`) records
it in `admin.audit_logs.reason` instead. `suspend_driver()` is given
the identical shape for forward consistency with whatever future router
composes it, once a real endpoint is documented — not speculative
infrastructure, the same signature an already-proven sibling command
already has. `reactivate_driver()` takes no reason, matching
`approve_driver()`'s equally reason-less shape (a reversal, not a
decision needing justification the way a rejection/suspension does).

5. Decision 4 — Suspend is reachable from any operational_status;
   reactivate always lands on OFFLINE, never ONLINE

No source document constrains which states `SuspendDriver` may be
called from, so `suspend_driver()` accepts OFFLINE/ONLINE/ON_RIDE/
INELIGIBLE alike — rejecting only an already-SUSPENDED driver
(`DriverAlreadySuspendedError`). It does **not** touch any in-progress
ride (`ride.rides`) if the driver happens to be ON_RIDE — no source
document describes force-cancelling an active ride as part of
suspension, and inventing that would be a real passenger-safety
decision this ADR does not make. `reactivate_driver()` always lands on
OFFLINE, never directly on ONLINE, mirroring ADR-0009's explicit
"approval does not change eligibility" precedent for
`ApproveVehicle`/`ApproveDriver` — a reactivated driver must explicitly
Go Online themselves through the existing, already-validated
`go_online()` path, not reappear as immediately dispatchable.

6. Decision 5 — `go_online()`'s "driver not suspended" precondition
   needed no new code, only a docstring/message correction

api-contracts.md §10 already anticipated this: "'Driver not suspended'
is not separately checked: SUSPENDED... is only reachable via
SuspendDriver... the precondition holds by construction until that
command exists, so implementing an explicit check now would be
unreachable dead code." Now that `SuspendDriver` exists,
`go_online()`'s existing generic guard (`operational_status is not
OFFLINE` → `INVALID_STATE_TRANSITION`) already covers SUSPENDED
correctly — both functionally and against api-contracts.md §10's own
documented error-code mapping (`INVALID_STATE_TRANSITION` for "Go
Online, driver not currently OFFLINE"). No new branch was added; the
docstring's now-stale "holds by construction" claim and the error
message's now-inaccurate "already ONLINE or ON_RIDE" wording (silent on
SUSPENDED/INELIGIBLE) are both corrected to describe what the check
actually enforces today.

7. Item 6 — Automatic, threshold-based suspension remains explicitly
   out of scope

BR-069 ("Repeated Driver Cancellation... Temporary suspension. Exact
thresholds and suspension duration are: TBD"), BR-119, and business-
rules.md §43's "Items Still TBD" list ("Exact strike thresholds",
"Suspension duration") all mark the automatic progressive-enforcement
path as a genuine, unresolved TBD — unchanged by this ADR. This task
builds only the manual, admin-triggered command
(`suspend_driver()`/`reactivate_driver()` as plain callable service
methods) — nothing here reads `driver.drivers.strikes` or auto-invokes
suspension at any threshold. Same treatment ADR-0015/0016 already gave
this exact TBD (BR-069/119's progressive-abuse escalation) for the
penalty/strike work.

8. Consequences — documents updated alongside this ADR

- `modules/driver/__init__.py` updated: SuspendDriver/ReactivateDriver
  moved from "not yet planned" to "service-layer complete, no HTTP
  endpoint documented."
- `docs/07-state-machines/state-machines.md` §67 updated: it explicitly
  deferred "which actor, which preconditions, which events" for
  SuspendDriver/ReactivateDriver to "whichever task actually implements
  each command" — this is that task, so §67 now records the actual
  transition rules (Decision 4/5 above) the same way it already records
  GoOnline/GoOffline's.
- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md` updated: this task marked
  complete for the scope above.
- No content changed in `business-rules.md`, `domain-design.md`,
  `event-contracts.md`, or `database-design.md` — the domain built
  matches what they already specify (§7.3's state, §7.4's commands)
  with nothing contradicted.
