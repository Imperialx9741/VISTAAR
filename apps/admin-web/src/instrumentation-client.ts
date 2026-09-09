import * as Sentry from "@sentry/nextjs";

import { scrubSentryEvent } from "./lib/monitoring/scrubSentryEvent";

/**
 * Client-side Sentry init (2026-09-08, owner decision — mirrors the
 * backend's own Sentry wiring, ADR-0053, and the mobile app's, as its
 * own separate Sentry project — `vistaar-3j` org — so admin-web
 * errors don't mix into either of those feeds).
 *
 * Uses Next.js 16's own file convention for this,
 * `instrumentation-client.ts` at the `src` root — confirmed directly
 * against this exact Next.js version's own bundled docs
 * (`node_modules/next/dist/docs/.../instrumentation-client.md`)
 * before writing this, per this app's own AGENTS.md warning not to
 * assume an older Next.js's conventions still apply. This is NOT the
 * older `sentry.client.config.ts` + `withSentryConfig` pattern
 * Sentry's own setup wizard still defaults to — that pattern predates
 * `instrumentation-client.ts` (introduced Next.js v15.3) and is not
 * what this file does.
 *
 * `NEXT_PUBLIC_SENTRY_DSN` (not a plain `SENTRY_DSN`) because this
 * file runs in the browser — only `NEXT_PUBLIC_`-prefixed env vars are
 * inlined into the client bundle (same convention this app's
 * `NEXT_PUBLIC_API_BASE_URL`, `src/lib/api/client.ts`, already uses).
 * A Sentry DSN is meant to be public (it is a write-only ingest
 * identifier, not an auth secret), so shipping it in the client bundle
 * is Sentry's own intended usage, not a leak. An empty/undefined DSN
 * (no `NEXT_PUBLIC_SENTRY_DSN` in `.env.local`) is `Sentry.init`'s own
 * documented disabled state — the same "wired, real credential arrives
 * later" pattern every other provider integration in this codebase
 * follows.
 */
Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NODE_ENV,
  // Cost/volume call for whoever holds the real Sentry account, not
  // this app to make blindly — same 0.1 default the backend (ADR-0053)
  // and the mobile app both use, not full tracing on every session.
  tracesSampleRate: 0.1,
  sendDefaultPii: false,
  beforeSend: scrubSentryEvent,
});
