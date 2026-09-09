import * as Sentry from "@sentry/nextjs";

import { scrubSentryEvent } from "./lib/monitoring/scrubSentryEvent";

function sentryOptions() {
  return {
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    environment: process.env.NODE_ENV,
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
    beforeSend: scrubSentryEvent,
  };
}

/**
 * Server/edge-side Sentry init — Next.js's own `instrumentation.ts`
 * file convention (`register()` is called once per server instance,
 * before it accepts any request; see `instrumentation-client.ts`'s own
 * doc comment for why this convention was used over an older wizard-
 * generated setup, confirmed against this exact Next.js version's own
 * bundled docs before writing this). `NEXT_RUNTIME` distinguishes the
 * Node.js server runtime from the separate Edge runtime, per Next.js's
 * own documented pattern for this file — this app doesn't currently
 * use Edge Middleware, but the check costs nothing and keeps this
 * correct if that ever changes.
 */
export function register() {
  if (process.env.NEXT_RUNTIME === "nodejs" || process.env.NEXT_RUNTIME === "edge") {
    Sentry.init(sentryOptions());
  }
}

// Forwards a server-rendering/route-handler/server-action error to
// Sentry — Next.js's own documented `onRequestError` hook (App
// Router, stable since Next.js v15), wired to this SDK's own helper
// for it (`Sentry.captureRequestError`) rather than hand-rolling the
// request/context mapping ourselves.
export const onRequestError = Sentry.captureRequestError;
