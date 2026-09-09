import type { ErrorEvent } from "@sentry/nextjs";

/**
 * Mirrors the same "never let OTP/access/refresh tokens reach a
 * third-party error tracker" discipline the backend
 * (`_scrub_sensitive_sentry_data`, `apps/backend/src/main.py`,
 * security.md §65, ADR-0053) and the mobile app
 * (`_scrubSensitiveSentryData`, `apps/mobile/lib/main.dart`) both
 * already apply — the admin console has its own sensitive values to
 * keep out of error reports: admin access/refresh tokens, and TOTP
 * MFA codes (ADR-0051), the same 6-digit shape mobile's customer OTP
 * already guards against. `sendDefaultPii: false` (set at both
 * `Sentry.init()` call sites this feeds — `instrumentation-client.ts`
 * and `instrumentation.ts`) already keeps request bodies/headers/IP
 * out of every event by default; this additionally redacts anything
 * *inside* an exception's own message, the one path
 * `sendDefaultPii` doesn't cover.
 */
export function scrubSentryEvent(event: ErrorEvent): ErrorEvent {
  const scrub = (value: string) =>
    value
      .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
      .replace(/\b\d{6}\b/g, "[redacted]");

  for (const exception of event.exception?.values ?? []) {
    if (exception.value) exception.value = scrub(exception.value);
  }
  return event;
}
