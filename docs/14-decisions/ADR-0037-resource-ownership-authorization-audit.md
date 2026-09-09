ADR-0037 — Resource-Ownership Authorization Audit

Status: Accepted.
Date recorded: 2026-08-26.
Deciders: Continuing autonomously under the owner's phase-level-autonomy
grant. No owner-level decision gate applies — this is a verification
pass over already-implemented code, not a new design decision.

1. Context

VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md's Phase 02 write-up named
"resource-ownership authorization" as "genuinely unblocked and not yet
built... an audit/formalization pass, not new capability." Before
starting this task, the same write-up's OTP-IP-dimension claim
("genuinely unblocked and not yet built") turned out to be stale —
`modules/identity/rate_limit.py`'s IP dimension was already fully
implemented, wired, and tested, just never reflected back into the
roadmap narrative. That discovery is the direct reason this task
verified the ownership-authorization claim against the actual code
before starting, rather than trusting the document's framing — the same
"a document is a claim to verify, not a directive to follow blind"
discipline this project's memory already applies to prior-session
lessons, now applied to this session's own earlier writing.

2. What was audited

Every router endpoint with a resource-ID path parameter, across every
module:
- `modules/ride/router.py`: `/{ride_id}/...` — cancel, driver-cancel,
  get, arrived, otp/refresh, start, complete, early-drop (+confirm),
  pickup-change (+driver-decision, +confirm), destination-change
  (+confirm), gps-disputes/{dispute_id} (+evidence endpoints).
- `modules/safety/router.py`: `/{ride_id}/sos`.
- `modules/support/router.py`: `/cases/{case_id}`.
- `modules/vehicle/router.py`: `/{vehicle_id}` (get/patch),
  `/{vehicle_id}/activate`, `/{vehicle_id}/deactivate`.
- `modules/admin/router.py`: excluded deliberately — every admin
  endpoint's whole point is that an authenticated admin may act on any
  resource; there is no "ownership" to check there in the same sense.
- `modules/promotion/router.py`, `modules/referral/router.py`,
  `modules/wallet/router.py`, `modules/customer/router.py`: no
  resource-ID path parameters exist at all (every endpoint is
  `/me`-scoped, reading the resource directly off the authenticated
  account) — no ownership-check gap is possible there by construction.

For each ride/safety/support/vehicle endpoint, confirmed (a) the
service-layer call passes the authenticated account's own ID alongside
the resource ID, (b) a mismatch and a genuinely-missing resource produce
the identical error code (never two different codes that would let a
caller distinguish "doesn't exist" from "not yours" — the IDOR-masking
pattern this codebase already names consistently in code comments
across advertisement, driver, matching, promotion, ride, safety, support,
and vehicle), and (c) a regression test exists asserting that behavior.

3. Finding

Every endpoint's ownership check itself was already correctly
implemented — no security gap existed. One test-coverage gap was found:
`POST /api/v1/rides/{ride_id}/destination-change` and
`.../destination-change/confirm` (built under ADR-0033 Decision 9) had
the correct check in `RideService.get_ride_for_destination_change()`/
`confirm_destination_change()` (verified: `ride.customer_id !=
customer_id` raises the same `RideNotFoundError` a missing ride would)
but no test asserting it — unlike its sibling `pickup-change` endpoints
and every other recently-added ride sub-resource (`early-drop`,
`gps-disputes`), which all already had an "unrelated account" test.

4. Resolution

Added `test_unrelated_customer_cannot_request_a_destination_change` and
`test_unrelated_customer_cannot_confirm_a_destination_change` to
`tests/test_destination_change_api.py`, mirroring the exact assertion
shape (`404`, `RIDE_NOT_FOUND`) `test_pickup_change_api.py`'s own
`test_unrelated_driver_cannot_decide_a_pickup_change` already
established for its sibling endpoint. Both pass against the existing,
unmodified router/service code — confirming the fix needed was in test
coverage, not application logic.

5. Consequences

- `docs/VISTAAR_AUTONOMOUS_EXECUTION_PLAN.md`'s Phase 01 and Phase 02
  write-ups are corrected: the Phase 01 claim about driver documents
  still using a placeholder (stale — ADR-0031 already retrofitted it)
  and the Phase 02 claim about the OTP IP dimension being unbuilt
  (stale — already implemented) are both fixed, alongside this task's
  own finding.
- No application code changed; this ADR records a verification pass
  and its one test-coverage fix, not a new design decision.
- Going forward, a document's "not yet built" claim about this
  codebase is a claim to verify against the actual code before treating
  it as a work item, not a directive to act on directly — this task
  found two stale instances of exactly that claim in the space of a
  single session segment.
