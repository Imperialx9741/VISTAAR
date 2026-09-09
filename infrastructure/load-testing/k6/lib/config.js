// Shared config/helpers for every VISTAAR k6 scenario (Phase 20,
// docs/10-testing/load-testing-plan-2026-09-03.md §5).
//
// Reads apps/mobile's own hardcoded polling intervals as the source of
// truth for pacing (matching the plan's §2 "grounded in the actual
// shipped client, not assumed") — duplicated here as constants rather
// than parsed from the Dart source, since k6 scripts can't import Dart;
// keep these in sync with sarthi_home_screen.dart /
// ride_status_screen.dart / ride_execution_screen.dart if those ever
// change.

export const BASE_URL = __ENV.API_BASE_URL || 'http://127.0.0.1:8000';

// apps/mobile/lib/features/home/sarthi_home_screen.dart
export const DRIVER_LOCATION_INTERVAL_S = 5;
export const DRIVER_OFFER_POLL_INTERVAL_S = 4;
// apps/mobile/lib/features/rides/ride_status_screen.dart,
// ride_execution_screen.dart
export const RIDE_STATUS_POLL_INTERVAL_S = 4;

// §1's working assumption — MUST be reconfirmed with the owner before
// sizing a real run against it (see the plan's own §1). Override via
// -e ONLINE_SARTHI_FRACTION=... etc. if a corrected split is confirmed.
export const ONLINE_SARTHI_FRACTION = Number(__ENV.ONLINE_SARTHI_FRACTION || 0.2);
export const ACTIVE_CUSTOMER_FRACTION = Number(__ENV.ACTIVE_CUSTOMER_FRACTION || 0.3);
// IDLE_FRACTION is implicitly 1 - the two above; idle sessions generate
// near-zero load (§1) and are deliberately not scripted as a scenario.

// §5.3's staged ramp — pass -e STAGE=smoke|baseline|design|target to
// pick one; VU counts below are the plan's own §5.3 numbers.
export const STAGES = {
  smoke: { vus: 50, duration: '2m' },
  baseline: { vus: 2500, duration: '10m' },
  design: { vus: 25000, duration: '15m' },
  target: { vus: 100000, duration: '20m' },
  soak: { vus: 25000, duration: '3h' }, // "design load, not target load" — §5.3 item 5
};

export function currentStage() {
  const name = __ENV.STAGE || 'smoke';
  const stage = STAGES[name];
  if (!stage) {
    throw new Error(
      `Unknown STAGE=${name}. Valid: ${Object.keys(STAGES).join(', ')}`,
    );
  }
  return { name, ...stage };
}

// Every scenario needs distinct authenticated identities — never one
// shared account (the plan's own §5.5 note: ADR-0061's rate limits are
// keyed per-identity and are expected to start rejecting traffic well
// before 100k users if VUs share one account). accounts.json is
// produced by setup/mint_test_accounts.py.
export function loadAccounts() {
  // eslint-disable-next-line no-undef -- k6's own SharedArray import,
  // done in each scenario file (open()/JSON.parse need the k6 runtime,
  // not importable cleanly from a shared lib without SharedArray).
  throw new Error('call loadAccountsFile(open(...)) from the scenario file instead');
}

export function partitionAccounts(allAccounts) {
  const drivers = allAccounts.filter((a) => a.role === 'DRIVER');
  const customers = allAccounts.filter((a) => a.role === 'CUSTOMER');
  return { drivers, customers };
}

export function authHeaders(token) {
  return { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } };
}

// api-contracts.md §3's envelope — every scenario's own checks() pull
// data out via this rather than re-parsing ad hoc.
export function envelopeOk(response) {
  if (response.status < 200 || response.status >= 300) return false;
  try {
    const body = response.json();
    return body && body.error === null;
  } catch (e) {
    return false;
  }
}
