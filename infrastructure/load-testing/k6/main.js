// VISTAAR Load Test — Phase 20 (docs/10-testing/load-testing-plan-2026-09-03.md).
//
// Implements §5.4's five weighted scenarios as k6 `scenarios`, each its
// own executor so per-scenario VU counts/weights are independent, and
// §5.3's staged ramp via -e STAGE=smoke|baseline|design|target|soak.
//
// PREREQUISITES:
//   1. Install k6: https://k6.io/docs/get-started/installation/
//   2. Run infrastructure/load-testing/setup/mint_test_accounts.py
//      against the target environment first — this script reads its
//      output (tokens.json) and does not create any accounts itself.
//
// USAGE:
//   k6 run -e API_BASE_URL=http://127.0.0.1:8000 -e STAGE=smoke \
//       -e ACCOUNTS_FILE=../tokens.json main.js
//
// Per-scenario VU split matches §5.4's weights (driver polling ~55%,
// ride status ~45% of *background polling* volume — the plan's own
// numbers exclude the low-frequency scenarios from that percentage
// split; those three run their own small, fixed VU pools regardless of
// STAGE, since scaling a full ride-lifecycle flow to 100k VUs would
// mean 100k concurrent real rides, which is a capacity claim about
// matching/ride throughput this test is not designed to make).

import { check, sleep } from 'k6';
import http from 'k6/http';
import { SharedArray } from 'k6/data';
import {
  BASE_URL,
  DRIVER_LOCATION_INTERVAL_S,
  DRIVER_OFFER_POLL_INTERVAL_S,
  RIDE_STATUS_POLL_INTERVAL_S,
  currentStage,
  authHeaders,
  envelopeOk,
} from './lib/config.js';

const accountsFile = __ENV.ACCOUNTS_FILE || '../tokens.json';

// SharedArray loads once and is shared read-only across all VUs —
// avoids every VU re-parsing a potentially large tokens.json.
const accounts = new SharedArray('accounts', function () {
  const raw = JSON.parse(open(accountsFile));
  return raw.accounts;
});

function driversOnly() {
  return accounts.filter((a) => a.role === 'DRIVER');
}
function customersOnly() {
  return accounts.filter((a) => a.role === 'CUSTOMER');
}
function adminOnly() {
  return accounts.find((a) => a.role === 'ADMIN');
}

const stage = currentStage();

// §5.4's low-frequency scenarios run a small, fixed pool regardless of
// STAGE — see the module comment above for why.
const RIDE_LIFECYCLE_VUS = Math.min(10, driversOnly().length, customersOnly().length);
const WALLET_RECHARGE_VUS = Math.min(5, driversOnly().length);
const ADMIN_REPORTING_VUS = 2;

export const options = {
  scenarios: {
    driver_polling: {
      executor: 'per-vu-iterations',
      vus: Math.min(stage.vus, driversOnly().length) || 1,
      iterations: 1000000, // effectively "run for the whole stage duration"
      maxDuration: stage.duration,
      exec: 'driverPolling',
    },
    ride_status_polling: {
      executor: 'per-vu-iterations',
      vus: Math.min(stage.vus, customersOnly().length) || 1,
      iterations: 1000000,
      maxDuration: stage.duration,
      exec: 'rideStatusPolling',
      startTime: '5s', // let driver_polling's VUs start first (closer to real traffic shape)
    },
    ride_lifecycle: {
      executor: 'per-vu-iterations',
      vus: RIDE_LIFECYCLE_VUS || 1,
      iterations: 1,
      maxDuration: stage.duration,
      exec: 'rideLifecycle',
    },
    wallet_recharge: {
      executor: 'constant-vus',
      vus: WALLET_RECHARGE_VUS || 1,
      duration: stage.duration,
      exec: 'walletRecharge',
    },
    admin_reporting: {
      executor: 'constant-vus',
      vus: ADMIN_REPORTING_VUS,
      duration: stage.duration,
      exec: 'adminReporting',
    },
  },
  // §5.5's per-endpoint latency/error thresholds — these are the
  // *acceptance criteria* a real run is judged against, not a claim
  // about what the current infrastructure will achieve (§6 of the
  // plan). Adjust once baseline-stage numbers establish a real
  // starting point.
  thresholds: {
    'http_req_duration{scenario:driver_polling}': ['p(95)<500', 'p(99)<1500'],
    'http_req_duration{scenario:ride_status_polling}': ['p(95)<500', 'p(99)<1500'],
    'http_req_duration{scenario:ride_lifecycle}': ['p(95)<2000'],
    'http_req_failed{scenario:driver_polling}': ['rate<0.01'],
    'http_req_failed{scenario:ride_status_polling}': ['rate<0.01'],
  },
};

// --- Driver background polling (§5.4, ~55% of background-polling volume) --

export function driverPolling() {
  const drivers = driversOnly();
  const driver = drivers[__VU % drivers.length];
  const opts = authHeaders(driver.token);

  const locationRes = http.post(
    `${BASE_URL}/api/v1/drivers/me/location`,
    JSON.stringify({
      latitude: 25.5941 + (Math.random() - 0.5) * 0.05,
      longitude: 85.1376 + (Math.random() - 0.5) * 0.05,
      accuracy_meters: 8,
      recorded_at: new Date().toISOString(),
    }),
    opts,
  );
  check(locationRes, { 'location update ok': (r) => envelopeOk(r) });

  const offersRes = http.get(`${BASE_URL}/api/v1/drivers/me/ride-offers`, opts);
  check(offersRes, { 'offer poll ok': (r) => envelopeOk(r) });

  sleep(Math.min(DRIVER_LOCATION_INTERVAL_S, DRIVER_OFFER_POLL_INTERVAL_S));
}

// --- Ride status polling (§5.4, ~45% of background-polling volume) -------
//
// Represents "a customer with an active ride, polling its status" (§1's
// working assumption's second traffic class) — creates one real ride
// first (SEARCHING has no assigned driver to poll meaningfully, but the
// GET itself still exercises the same read path this scenario measures),
// then polls it repeatedly for the rest of the iteration.

export function rideStatusPolling() {
  const customers = customersOnly();
  const customer = customers[__VU % customers.length];
  const opts = authHeaders(customer.token);

  const createRes = http.post(
    `${BASE_URL}/api/v1/rides`,
    JSON.stringify({
      pickup: { latitude: 25.5941, longitude: 85.1376 },
      destination: { latitude: 25.612, longitude: 85.158 },
      vehicle_category: 'CAB',
      cab_tier: 'ECO',
      payment_method: 'ONLINE',
    }),
    Object.assign({}, opts, {
      headers: Object.assign({}, opts.headers, {
        'Idempotency-Key': `loadtest-${__VU}-${__ITER}-${Date.now()}`,
      }),
    }),
  );
  if (!check(createRes, { 'ride created': (r) => r.status === 201 })) {
    sleep(RIDE_STATUS_POLL_INTERVAL_S);
    return;
  }
  const rideId = createRes.json('data.ride_id');

  const pollsPerIteration = 5; // a short representative burst, not the whole stage duration
  for (let i = 0; i < pollsPerIteration; i++) {
    const statusRes = http.get(`${BASE_URL}/api/v1/rides/${rideId}`, opts);
    check(statusRes, { 'ride status poll ok': (r) => envelopeOk(r) });
    sleep(RIDE_STATUS_POLL_INTERVAL_S);
  }
}

// --- Full ride lifecycle (§5.4, low frequency, high importance) ----------
//
// OTP request/verify is replaced by the pre-minted token from
// mint_test_accounts.py (see that script's own docstring for why) —
// everything from ride creation onward is real: matching dispatch,
// offer accept, arrival/start/complete, and the resulting wallet debit.

export function rideLifecycle() {
  const drivers = driversOnly();
  const customers = customersOnly();
  const driver = drivers[__VU % drivers.length];
  const customer = customers[__VU % customers.length];
  const driverOpts = authHeaders(driver.token);
  const customerOpts = authHeaders(customer.token);

  http.post(
    `${BASE_URL}/api/v1/drivers/me/online`,
    null,
    driverOpts,
  );
  http.post(
    `${BASE_URL}/api/v1/drivers/me/location`,
    JSON.stringify({
      latitude: 25.5941,
      longitude: 85.1376,
      accuracy_meters: 8,
      recorded_at: new Date().toISOString(),
    }),
    driverOpts,
  );

  const createRes = http.post(
    `${BASE_URL}/api/v1/rides`,
    JSON.stringify({
      pickup: { latitude: 25.5941, longitude: 85.1376 },
      destination: { latitude: 25.612, longitude: 85.158 },
      vehicle_category: 'CAB',
      cab_tier: 'ECO',
      payment_method: 'ONLINE',
    }),
    Object.assign({}, customerOpts, {
      headers: Object.assign({}, customerOpts.headers, {
        'Idempotency-Key': `loadtest-lifecycle-${__VU}-${Date.now()}`,
      }),
    }),
  );
  if (!check(createRes, { 'ride created': (r) => r.status === 201 })) return;
  const rideId = createRes.json('data.ride_id');

  // Matching dispatch is async (Redis-backed) — poll briefly for the
  // offer to appear rather than assuming it's instant.
  let offerId = null;
  for (let attempt = 0; attempt < 5 && !offerId; attempt++) {
    sleep(1);
    const offersRes = http.get(`${BASE_URL}/api/v1/drivers/me/ride-offers`, driverOpts);
    const offers = offersRes.json('data.offers') || [];
    const pending = offers.find((o) => o.ride_id === rideId && o.status === 'PENDING');
    if (pending) offerId = pending.offer_id;
  }
  if (!check(offerId, { 'offer received': (id) => id !== null })) return;

  const acceptRes = http.post(
    `${BASE_URL}/api/v1/drivers/me/ride-offers/${offerId}/accept`,
    null,
    Object.assign({}, driverOpts, {
      headers: Object.assign({}, driverOpts.headers, {
        'Idempotency-Key': `loadtest-accept-${__VU}-${Date.now()}`,
      }),
    }),
  );
  check(acceptRes, { 'offer accepted': (r) => envelopeOk(r) });

  const arrivedRes = http.post(
    `${BASE_URL}/api/v1/rides/${rideId}/arrived`,
    JSON.stringify({ latitude: 25.5941, longitude: 85.1376 }),
    driverOpts,
  );
  check(arrivedRes, { 'arrived ok': (r) => envelopeOk(r) });

  const otpRes = http.post(
    `${BASE_URL}/api/v1/rides/${rideId}/otp/refresh`,
    null,
    customerOpts,
  );
  const otp = otpRes.json('data.otp');

  const startRes = http.post(
    `${BASE_URL}/api/v1/rides/${rideId}/start`,
    JSON.stringify({ otp: otp }),
    driverOpts,
  );
  check(startRes, { 'ride started': (r) => envelopeOk(r) });

  const completeRes = http.post(
    `${BASE_URL}/api/v1/rides/${rideId}/complete`,
    JSON.stringify({ latitude: 25.612, longitude: 85.158 }),
    driverOpts,
  );
  check(completeRes, { 'ride completed (wallet debit happens here)': (r) => envelopeOk(r) });

  http.post(`${BASE_URL}/api/v1/drivers/me/offline`, null, driverOpts);
}

// --- Wallet recharge (§5.4, low frequency) --------------------------------
//
// Order creation only — Razorpay TEST credentials (ADR-0060). Never
// completes a real checkout (that needs Razorpay's own client SDK, out
// of scope for a backend capacity test) — "never load-test against a
// real payment gateway" (§5.4's own explicit instruction).

export function walletRecharge() {
  const drivers = driversOnly();
  const driver = drivers[__VU % drivers.length];
  const opts = authHeaders(driver.token);

  const res = http.post(
    `${BASE_URL}/api/v1/drivers/me/wallet/recharge`,
    JSON.stringify({ amount: 500 }),
    opts,
  );
  check(res, { 'recharge order created': (r) => envelopeOk(r) });
  sleep(10);
}

// --- Admin/reporting (§5.4, low frequency, separate VU pool) --------------

export function adminReporting() {
  const admin = adminOnly();
  if (!admin) return; // mint_test_accounts.py always seeds one; defensive only
  const opts = authHeaders(admin.token);

  const endpoints = [
    '/api/v1/admin/reports/rides',
    '/api/v1/admin/reports/drivers',
    '/api/v1/admin/reports/financial',
  ];
  const path = endpoints[Math.floor(Math.random() * endpoints.length)];
  const res = http.get(`${BASE_URL}${path}`, opts);
  check(res, { 'admin report ok': (r) => envelopeOk(r) });
  sleep(5);
}

// --- Result reporting (Phase 20's "result/reporting tooling") ------------
//
// k6's own JSON summary (machine-readable, for the analyze script below)
// plus a plain-text console summary — no external dependency needed.

export function handleSummary(data) {
  return {
    stdout: JSON.stringify(
      { stage: stage.name, metrics_summary: 'see reports/summary.json for full detail' },
      null,
      2,
    ),
    [`../reports/summary-${stage.name}-${Date.now()}.json`]: JSON.stringify(data, null, 2),
  };
}
