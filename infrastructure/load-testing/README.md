# VISTAAR Load Testing

Phase 20 implementation of `docs/10-testing/load-testing-plan-2026-09-03.md`
— real, runnable local preparation for that plan's §5 methodology.
**No test has been executed against a real target environment from this
change** — see that plan's own §6 for what remains a claim-free "plan,
not a promise," and the section below for exactly what has vs. hasn't
been verified.

## What's here

```
setup/
  mint_test_accounts.py     Provisions N real driver + M real customer
                             accounts (documents approved, vehicle
                             approved/active, wallet funded) and mints
                             real access tokens for all of them —
                             see that script's own docstring for why
                             this deliberately bypasses OTP/SMS.
  cleanup_test_accounts.py  Removes everything the script above created.
k6/
  main.js                   All five §5.4 scenarios, staged via
                             -e STAGE=smoke|baseline|design|target|soak.
  lib/config.js             Shared constants (polling intervals, stage
                             VU counts, auth/envelope helpers).
reports/
  analyze_summary.py        Turns a k6 JSON summary into a pass/fail
                             Markdown report against main.js's own
                             thresholds.
```

## Running a test

```bash
# 1. Provision accounts (run from apps/backend's own venv)
cd apps/backend && source .venv/Scripts/activate
python ../../infrastructure/load-testing/setup/mint_test_accounts.py \
    --drivers 200 --customers 300 \
    --api-base-url http://<target-host>:8000 \
    --i-understand-this-is-not-production \
    --out ../../infrastructure/load-testing/tokens.json

# 2. Run the smoke stage first, always (plan §5.3 item 1 — "catches
#    scripting bugs cheaply" before spending real VU-hours)
cd ../../infrastructure/load-testing/k6
k6 run -e API_BASE_URL=http://<target-host>:8000 -e STAGE=smoke main.js

# 3. Analyze the result
python ../reports/analyze_summary.py ../reports/summary-smoke-<ts>.json

# 4. Clean up
cd ../../../apps/backend
python ../../infrastructure/load-testing/setup/cleanup_test_accounts.py \
    --i-understand-this-is-not-production
```

For `baseline`/`design`/`target`/`soak`, provision proportionally more
accounts first (`--drivers`/`--customers` should comfortably exceed the
stage's VU count — see `k6/lib/config.js`'s `STAGES`).

## What has been verified locally (2026-09-04)

- `mint_test_accounts.py` and `cleanup_test_accounts.py`: run for real
  against the local dev backend + Postgres, end to end, at up to 5
  concurrent Sarthi provisioning tasks — every minted driver token was
  used to call the real `POST /drivers/me/online` and
  `POST /drivers/me/location` endpoints and all succeeded; cleanup
  removed every row created, confirmed by a direct row-count query
  before and after. Three real bugs were found and fixed during this
  verification:
  - A missing `::uuid[]` cast on the bulk-delete queries.
  - A missing `admin.audit_logs` cleanup step before deleting the admin
    row (the admin-approve calls the setup script itself makes write
    real audit-log rows).
  - A genuine concurrency-only flakiness: running several driver-
    provisioning tasks at once occasionally left a document's raw-SQL
    "mark APPROVED" step silently not applied (the same UPDATE always
    succeeded when run in isolation) — reproduced consistently at 3+
    concurrent tasks, fixed by having `_approve_document_with_retry()`
    check the UPDATE's `rowcount` and retry briefly instead of assuming
    the first attempt always lands; also added explicit status-code
    checks on the admin-approve/activate HTTP calls so a real failure
    there is never silent either. Re-verified after the fix: 5
    concurrent Sarthi provisions, all 5 reached ONLINE successfully.
- `main.js`/`lib/config.js`: syntax-checked (`node --check`); every
  endpoint path and request body was cross-checked directly against
  the real router source (`modules/*/router.py`), not assumed — one
  real error was caught this way (an assumed `POST .../vehicles/
  documents` endpoint did not exist at the time; vehicle document
  submission had no HTTP endpoint anywhere in this codebase, only a
  service-layer method, so `mint_test_accounts.py` seeded those rows
  directly instead). **Since fixed** — ADR-0072 (2026-09-04) added the
  real endpoint, and `mint_test_accounts.py` now calls it for real
  (still marking the result APPROVED via raw SQL afterward — approval
  itself remains admin-only with no bulk HTTP endpoint).
- `analyze_summary.py`: run against a hand-built representative k6
  summary JSON and produced a correct Markdown report.

## What has NOT been verified (environment-dependent, per the plan's §5.2)

- **k6 itself has not been run** — it is not installed in this
  development environment. `main.js` has only been syntax-checked, not
  executed; a first real `k6 run -e STAGE=smoke` against a live backend
  is the natural next step once k6 is available, and would very likely
  surface small issues no static check can catch (e.g. an actual
  matching-dispatch timing assumption in `rideLifecycle()`'s offer-poll
  retry loop).
- **No staging AWS environment exists to test against** (plan §5.2 —
  "this cannot run in the current environment... blocked on AWS
  access"). Every VU count above `smoke` in this preparation is sized
  for that eventual environment, not this local one — running `design`
  or `target` against a local dev server would not produce a meaningful
  result even if it happened not to crash.

## Owner items still open (plan §1, unchanged by this implementation)

- The 20/30/50 online-Sarthi/active-customer/idle traffic-mix split is
  still an unconfirmed working assumption — override via
  `-e ONLINE_SARTHI_FRACTION=...`/`-e ACTIVE_CUSTOMER_FRACTION=...` once
  confirmed or corrected.
