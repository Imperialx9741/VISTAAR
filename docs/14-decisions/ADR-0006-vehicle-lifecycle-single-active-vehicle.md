ADR-0006 — Vehicle Lifecycle: Single Active Vehicle Per Driver

Status: Accepted (business decision — approved, per the task that
requested this record)
Date recorded: 2026-08-21
Deciders: Approved as part of the "Vehicle Lifecycle Decision & API
Contract Clarification" task, following up on Phase 2 / Task 2.4
(Vehicle Management), which had explicitly left this question open (see
state-machines.md §68.2's prior draft and that task's final report,
section X.1).

1. Problem

Task 2.4 implemented vehicle Activate/Deactivate exactly as documented in
`api-contracts.md` §11 ("Vehicle approved AND Driver OFFLINE"), but found
that no source document explicitly stated whether a driver could have
more than one vehicle simultaneously `ACTIVE`. `business-rules.md` BR-102
and `PRD.md` §10 describe "Select approved vehicle → Activate it" as a
singular action, and `domain-design.md` §8.4 said "Only an approved and
active vehicle may be used for matching" — suggestive, but not an
explicit exclusivity rule. Task 2.4 correctly declined to invent one.

2. Decision

The following is now an approved VISTAAR business rule:

    One driver
        ↓
    Multiple registered vehicles allowed
        ↓
    Maximum ONE ACTIVE vehicle per driver
        ↓
    Vehicle switching is allowed only while the driver is OFFLINE

Recorded in `business-rules.md` as BR-122 (see that document — numbered
out of sequence, placed alongside BR-099–BR-102 since it belongs to the
same Vehicle Verification topic; §44's change-policy "Update Business
Rules" step is satisfied by that addition).

3. Enforcement

- **Application level**: `VehicleService.activate_vehicle()` locks every
  one of the driver's vehicle rows (`SELECT ... FOR UPDATE`, via the new
  `VehicleRepository.list_by_driver_for_update()`) before any check or
  write. Any other `ACTIVE` vehicle for the same driver is deactivated as
  part of the same transaction, immediately before the target vehicle is
  activated. This serializes concurrent activation requests for the same
  driver — a second request blocks until the first commits, then
  re-reads the now-current state.
- **Database level**: a partial unique index,
  `uq_vehicles_one_active_per_driver`, on
  `vehicle.vehicles(driver_id) WHERE operational_status = 'ACTIVE'`
  (migration `1f10a4e53685`). This is the unconditional backstop — no
  interleaving of transactions can leave two rows with the same
  `driver_id` both `ACTIVE`, independent of whether the application-level
  locking above behaves as intended.
- `SqlAlchemyVehicleRepository.save()` catches the `IntegrityError` this
  index would raise (should the backstop ever actually be needed) and
  translates it to `VehicleActivationConflictError`
  (`INVALID_STATE_TRANSITION`) rather than surfacing a raw database error
  to the client.
- Verified with a real-PostgreSQL test that fires two genuinely
  concurrent HTTP activation requests (via `ThreadPoolExecutor`, real OS
  threads, real independent DB connections per request) for two
  different vehicles belonging to the same driver, then confirms via a
  direct SQL query that exactly one vehicle ended up `ACTIVE`. Run
  repeatedly (5 consecutive runs) to rule out a false pass.

4. Consequences

- `database-design.md` §8.1 documents the new index and a new §8.1.1
  ("Vehicle Activation Transaction") describing the enforcement sequence.
- `api-contracts.md` §11's Activate Vehicle documentation now states the
  auto-deactivation side effect explicitly.
- `state-machines.md` §68.2/§68.3 updated: the previously-open question
  is resolved and cross-referenced to this ADR and to BR-122.
- `domain-design.md` §8.4 updated with the exclusivity rule.
- This does not change Add Vehicle, verification_status, or any
  document-verification-related behavior — those remain exactly as Task
  2.4 left them (all still out of scope, see that task's final report,
  sections M–Q).
- This ADR does not resolve Task 2.4's second open item (whether
  Deactivate independently requires `verification_status = APPROVED`) —
  see `state-machines.md` §68.2's remaining note; that question was not
  part of this task's scope.

5. API contract additions made alongside this decision

`GET /api/v1/drivers/me/vehicles/{vehicle_id}` and
`PATCH /api/v1/drivers/me/vehicles/{vehicle_id}` were added (Task 2.4 had
correctly declined to add them as undocumented). PATCH accepts only
`make`/`model` — `category` and `registration_number` are excluded
because changing either is a materially different vehicle-identity
change with no documented flow (business-rules.md BR-099/BR-100's "add
another vehicle" is the only supported path for a different
category/registration number), and `driver_id`/`verification_status`/
`operational_status`/timestamps are server-controlled. See
`api-contracts.md` §11 for the full documented contract.
