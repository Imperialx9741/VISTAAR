/**
 * Client-side session accessor. Originally documented as "no login
 * screen writes this yet" (2026-08-28) — superseded 2026-09-08:
 * `LoginPage` (`src/components/auth/LoginPage.tsx`) now writes a real
 * session via [setAdminSession] after a genuine
 * `POST /api/v1/auth/otp/verify` (+ `/mfa/verify` if the admin has MFA
 * enabled, ADR-0051). [setAdminToken]/[clearAdminToken] are kept as
 * they were for manual local testing — still useful when you have a
 * raw access token (e.g. from `/docs`) and want to skip the login
 * screen — but the refresh token they don't touch means a session set
 * that way can't survive an access-token expiry the way a real login
 * can.
 */

const TOKEN_KEY = "vistaar_admin_token";
const REFRESH_TOKEN_KEY = "vistaar_admin_refresh_token";

export function getAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    // Private-browsing / storage-blocked contexts throw on access, not
    // just on write — treat exactly like "no session" rather than crash.
    return null;
  }
}

export function getAdminRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAdminToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Storage unavailable — nothing this function can do about that.
  }
}

export function clearAdminToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Same as above.
  }
}

/** Written by [LoginPage] on a successful sign-in (with or without an
 * MFA step) — stores both tokens the backend's `otp/verify`/
 * `mfa/verify` response returns, not just the access token. There is
 * no refresh-on-401 interceptor built yet (a real, disclosed gap, not
 * silently solved here) — `apiGet`/`apiPost` still only ever attach
 * [getAdminToken]'s access token, so a session still ends at
 * `expires_in` and requires signing in again; storing the refresh
 * token now at least means that future interceptor has something real
 * to read. */
export function setAdminSession(tokens: {
  accessToken: string;
  refreshToken: string;
}): void {
  setAdminToken(tokens.accessToken);
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refreshToken);
  } catch {
    // Storage unavailable — nothing this function can do about that.
  }
}

/** Clears both tokens — call after `POST /api/v1/auth/logout` (best
 * effort; the local session is cleared either way) or when a stored
 * session turns out to be invalid. */
export function clearAdminSession(): void {
  clearAdminToken();
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    // Same as above.
  }
}
