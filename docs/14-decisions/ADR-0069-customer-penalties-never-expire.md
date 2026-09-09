ADR-0069 — Customer Penalties Never Expire

Status: Accepted and implemented (2026-09-04) — owner business-rule
correction
Date recorded: 2026-09-04
Deciders: Project owner (explicit written decision).
Supersedes: BR-049 and BR-053's original 30-day-expiry reading
(business-rules.md), ADR-0015 §3/§6's `expires_at`/EXPIRED description,
state-machines.md §40/§41's EXPIRED penalty state and 30-day-expiry
section, and every place the `penalty.penalties.expires_at` column or
`PenaltyStatus.EXPIRED` value was implemented, documented, or returned
over HTTP.

1. Context

BR-049 (Customer Cancellation Charge) and BR-053 (No-Show Charge) were
originally read, and implemented from ADR-0015 (2026-08-23) onward, as
giving every customer penalty a 30-day validity window: a
`penalty.penalties.expires_at` column was stamped at creation
(`issued_at + 30 days`), a `PenaltyStatus.EXPIRED` value existed in the
schema and state machine, and `expires_at` was returned in the
cancellation-charge HTTP response and displayed in Admin Web.

No expiry *enforcement* was ever actually built — there was never a
background job that transitioned an OUTSTANDING penalty to EXPIRED, and
`PenaltyStatus.EXPIRED` was never produced by any code path in this
codebase, even before this correction. The column and status value
existed as unenforced, dormant scaffolding for a policy that state-
machines.md §41 itself flagged as unresolved ("the exact behavior after
expiry must follow the final approved penalty policy").

The owner's 2026-09-04 instruction resolves that open policy question
directly, and in the opposite direction from what the scaffolding
implied: customer penalties in VISTAAR never expire. Once created, a
penalty remains OUTSTANDING — collectible and displayed — indefinitely,
until the customer actually pays it (SETTLED) or an admin waives it
(WAIVED). There is no automatic expiry date, no time-based transition
out of OUTSTANDING, and no expiry enforcement job is to be built, ever,
for this penalty type.

2. Decision

1. **`expires_at` is removed, not merely unused.** The
   `penalty.penalties.expires_at` column is dropped (migration
   `b1d4e7f9a2c3`), not just left nullable-and-unread — a dead column
   that Admin Web actively displayed as a real (but never enforced)
   expiry date is worse than no column at all, and every real usage of
   it across the codebase was traced and removed rather than papered
   over.
2. **`PenaltyStatus.EXPIRED` is removed.** Confirmed via full-codebase
   search to have zero real usages anywhere before this correction — no
   code path ever produced it — making its removal a pure dead-code
   deletion, not a behavior change. The enum's final states are
   `OUTSTANDING`, `SETTLED`, `WAIVED`.
3. **`CUSTOMER_CHARGE_VALIDITY_DAYS = 30` is removed** from
   `penalty/domain/entities.py`; neither `new_customer_cancellation()`
   nor `new_scheduled_ride_late_cancellation()` computes or stamps an
   expiry any longer.
4. **No expiry enforcement job is built.** Explicitly instructed by the
   owner and consistent with the fact that none ever existed — this ADR
   closes state-machines.md §41's open policy question by deciding
   there is nothing to enforce, not by building the job the original
   scaffolding implied was still pending.
5. **BR-049 and BR-053 are corrected**, not merely re-interpreted, in
   business-rules.md: both now state the charge never expires and
   remains collectible until paid, explicitly citing this ADR.

3. Distinction from Sarthi cancellation-penalty debt (ADR-0062)

This ADR affects only `penalty.penalties` — the customer-side
cancellation/no-show/scheduled-late-cancellation charge (BR-047/048/
052/135), owed by a *customer* to VISTAAR (and, since ADR-0066, settled
via the Sarthi at the customer's next ride).

It has no effect on `wallet.wallets.outstanding_debt` — the Sarthi
cancellation-penalty debt mechanism ADR-0062 introduced, owed by a
*driver* to VISTAAR when a driver's wallet balance can't cover a
cancellation penalty at the time it's charged, recovered from that
driver's next wallet recharge. That mechanism never had an expiry
concept, is unaffected by this correction, and remains a structurally
separate code path (`wallet` module, not `penalty` module) — the two
must not be conflated. Similarly, ADR-0066's `TransactionType.
CASH_SETTLEMENT` driver-wallet debit (how VISTAAR recovers its share of
a settled customer penalty from the Sarthi) is unaffected: it already
never depended on `expires_at`, and a penalty now simply stays attached
and collectible on whatever ride eventually completes or gets
cancelled, however long that takes (see ADR-0066's updated §8).

4. What was changed

Backend:
- `penalty/domain/entities.py` — `expires_at` field, `CUSTOMER_CHARGE_
  VALIDITY_DAYS` constant, and `PenaltyStatus.EXPIRED` removed;
  `Penalty` dataclass, both factory methods, and the `waive()` docstring
  updated accordingly.
- `penalty/domain/errors.py`, `penalty/service.py`, `penalty/__init__.py`
  — docstrings correcting stale "SETTLED/EXPIRED/WAIVED" and
  "expires_at left untouched" language.
- `penalty/models.py` — `expires_at` column dropped; `idx_open_
  penalties` narrowed from `(user_id, expires_at)` to `(user_id)`
  (still serves its real query pattern — "does this user have any
  OUTSTANDING penalty" — which never needed `expires_at`).
- `penalty/repositories.py` — `expires_at` removed from ORM↔domain
  mapping in both directions.
- `admin/router.py` — `expires_at` removed from the admin penalty
  response dict (`_VALID_PENALTY_STATUSES`, being `frozenset(status.
  value for status in PenaltyStatus)`, needed no separate fix).
- `ride/router.py` — `expires_at` removed from both cancellation-charge
  response builders (`_post_acceptance_cancellation_charge()`,
  `_scheduled_ride_cancellation_charge()`); this was a real bug caught
  during this correction — both functions still referenced the
  already-removed `Penalty.expires_at` field, which would have raised
  `AttributeError` the next time a customer cancellation charge was
  returned.
- Migration `b1d4e7f9a2c3` — drops the column and old index, creates
  the narrowed index; verified with a full upgrade/downgrade/upgrade
  round-trip against a disposable Postgres container, including a
  round-trip with a real populated OUTSTANDING row present.

Tests:
- `tests/test_penalty_service.py` — `test_charge_expires_in_thirty_days`
  replaced with `test_customer_penalties_never_expire`.
- Full relevant suite re-run after the `ride/router.py` fix
  (`test_ride_api.py`, `test_ride_lifecycle_api.py`,
  `test_penalty_service.py`, `test_e2e_wallet_penalty_journey.py`): 76
  passed. `ruff`/`mypy` clean on every touched file.

Documentation:
- `business-rules.md` — BR-049, BR-053 rewritten; a summary line
  claiming every charge "has its own expiry date" corrected.
- `database-design.md` §26.1 — `expires_at TIMESTAMPTZ NOT NULL` column
  removed from the `penalty.penalties` DDL; the documented `status`
  value list no longer includes EXPIRED.
- `state-machines.md` §40/§41 — EXPIRED removed from the Penalty State
  Machine; §41 rewritten from "30-day expiry, behavior TBD" to state
  the corrected, now-decided rule and cross-reference this ADR.
- `api-contracts.md` §19 (post-acceptance and SCHEDULED cancellation
  charge shapes) and §48 (Admin Penalty Review) — `expires_at` removed
  from every documented response shape.
- ADR-0015 (§3/§6), ADR-0057 (§4), ADR-0066 (§8) — annotated as
  superseded on this specific point only, consistent with this project's
  practice of annotating historical ADRs rather than rewriting them; no
  other decision in any of those three ADRs is affected.

Admin Web (`apps/admin-web`):
- `lib/api/types.ts` — `EXPIRED` removed from the `PenaltyStatus` type;
  `expires_at` removed from the Penalty interface.
- `components/penalties/PenaltiesPage.tsx` — `EXPIRED` removed from the
  status filter; the `expires_at` column removed from the penalties
  table.
- `lib/status-tone.ts` — deliberately left untouched: its `EXPIRED` case
  is shared across multiple unrelated domains, and `GpsDisputeStatus`
  (ADR-0032's 24-hour evidence window) has its own legitimate EXPIRED
  state that must keep rendering correctly. Only the penalty screen
  stops ever invoking this helper with `"EXPIRED"`, which follows
  naturally from the backend no longer producing it.

5. What this ADR explicitly does not do

- Does not implement a penalty-expiry enforcement job — explicitly
  instructed not to, and consistent with the fact none ever existed.
- Does not change any penalty amount or qualification rule (BR-047/048/
  052/135 amounts and thresholds are untouched).
- Does not change ADR-0066's attach/release/settle mechanism — only the
  one sentence in its §8 describing what happens to a penalty attached
  to a ride that never completes or cancels, which no longer references
  an expiry that doesn't exist.
- Does not touch `wallet.wallets.outstanding_debt` (Sarthi cancellation-
  penalty debt, ADR-0062) in any way — see §3 above.
- Does not introduce a customer-facing penalty payment gateway — out of
  scope here and unaffected by this correction (ADR-0066 already
  settled how a customer penalty gets collected, via the Sarthi).

6. Verification

- Full-codebase search for every `expires_at`/`EXPIRED` occurrence,
  confirming every remaining hit belongs to an unrelated domain
  (matching offers, GPS disputes, driver/vehicle documents, identity
  OTP challenges/sessions, promotion entitlements, S3 presigned upload
  targets) and none belong to `penalty.penalties`.
- Migration round-trip against a disposable Postgres container (empty
  schema, and again with a real seeded OUTSTANDING row) confirming
  `expires_at` is genuinely absent post-upgrade and the downgrade path
  doesn't violate the old NOT NULL constraint.
- `ruff check` / `mypy` clean on every backend file touched.
- 76 backend tests passed across the ride/penalty/wallet-penalty-journey
  suites, including the new `test_customer_penalties_never_expire`.
