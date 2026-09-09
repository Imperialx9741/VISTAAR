import type { ApiEnvelope } from "./types";
import {
  clearAdminSession,
  getAdminRefreshToken,
  getAdminToken,
  setAdminSession,
} from "./session";

/**
 * Base URL for the real FastAPI backend (apps/backend). Swappable via
 * env — set NEXT_PUBLIC_API_BASE_URL in .env.local once a real
 * deployment/base URL is confirmed; defaults to the backend's local dev
 * address (docker-compose.dev.yml / `uvicorn` default).
 */
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

/** Thrown when there's no session token to attach — distinct from a real
 * ApiError so callers (the data layer) can tell "never even tried" apart
 * from "the backend said no." */
export class NoSessionError extends Error {
  constructor() {
    super("No admin session token is set.");
    this.name = "NoSessionError";
  }
}

interface TokenPairResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

/**
 * Auto-refresh on an expired access token (2026-09-08) — mirrors the
 * mobile app's own proven design exactly (`ApiClient.onAuthInvalid` +
 * `AuthSession._refreshTokens`, ADR-0076, `apps/mobile/lib/core/api/
 * api_client.dart` / `features/auth/auth_session.dart`), not a new
 * pattern invented for this app. Access tokens expire after
 * `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (30 by default,
 * `core/config.py`) — without this, every admin session dead-ends in
 * a full re-login every 30 minutes.
 *
 * `refreshInFlight` makes concurrent 401s (e.g. the Dashboard's own
 * three parallel calls) share exactly one real refresh call instead of
 * racing three — the same single-flight guard the mobile app's own
 * `_refreshInFlight` uses, same reasoning: a second/third refresh
 * attempt with a refresh token the first call may have already
 * rotated would itself fail.
 */
let refreshInFlight: Promise<string | null> | null = null;

function refreshAccessToken(): Promise<string | null> {
  return (refreshInFlight ??= doRefresh().finally(() => {
    refreshInFlight = null;
  }));
}

async function doRefresh(): Promise<string | null> {
  const refreshToken = getAdminRefreshToken();
  if (!refreshToken) return null;
  try {
    const data = await authPost<TokenPairResponse>("/api/v1/auth/refresh", {
      refresh_token: refreshToken,
    });
    setAdminSession({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
    });
    return data.access_token;
  } catch {
    // The refresh token itself is no longer usable — there is no
    // session left to keep. Same as the mobile app: sign out for real
    // rather than leaving a half-valid session sitting in storage.
    clearAdminSession();
    return null;
  }
}

async function fetchEnvelope<T>(
  url: URL,
  init: RequestInit,
): Promise<ApiEnvelope<T>> {
  const response = await fetch(url.toString(), init);
  const envelope = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || envelope.error) {
    const code = envelope.error?.code ?? "UNKNOWN_ERROR";
    const message = envelope.error?.message ?? response.statusText;
    throw new ApiError(code, message, response.status);
  }
  return envelope;
}

/**
 * Runs [attempt] with [token] first. On an `AUTH_INVALID` failure
 * (an expired/revoked access token — `AUTH_REQUIRED`, no token sent
 * at all, is never retried, there being nothing to refresh from
 * context), obtains a fresh access token via [refreshAccessToken] and
 * retries [attempt] exactly once with it. Any other error, or a
 * `null` refresh result (refresh itself failed), propagates the
 * original error unchanged — matching the mobile app's own
 * `ApiClient._withAuthRetry` precisely.
 */
async function withAuthRetry<T>(
  token: string,
  attempt: (token: string) => Promise<T>,
): Promise<T> {
  try {
    return await attempt(token);
  } catch (error) {
    if (!(error instanceof ApiError) || error.code !== "AUTH_INVALID") {
      throw error;
    }
    const newToken = await refreshAccessToken();
    if (newToken === null) throw error;
    return attempt(newToken);
  }
}

/**
 * Thin fetch wrapper around every GET this app makes against the real
 * admin API. Attaches the bearer token from lib/api/session.ts, unwraps
 * the standard {data, error, request_id} envelope (api-contracts.md §3),
 * and throws ApiError on a non-null `error` or a non-2xx response so
 * every call site can use one try/catch shape.
 */
export async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | undefined>,
): Promise<T> {
  const token = getAdminToken();
  if (!token) throw new NoSessionError();

  const url = new URL(path, API_BASE_URL);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }

  const envelope = await withAuthRetry(token, async (t) =>
    fetchEnvelope<T>(url, {
      headers: { Authorization: `Bearer ${t}` },
      cache: "no-store",
    }),
  );

  // A 2xx response with a null error always carries data per the
  // envelope's own contract — this cast documents that invariant rather
  // than re-deriving it at every call site.
  return envelope.data as T;
}

/**
 * POST/PATCH counterpart to apiGet. Unlike apiGet, callers of these two
 * (Admin Management's create/permission-update/disable/enable) must
 * never fall back to sample data on failure — a mutation against a real
 * admin account is not something a UI should ever silently pretend
 * succeeded. Every call site here surfaces the thrown ApiError/
 * NoSessionError as a real error state instead.
 */
async function apiMutate<T>(
  method: "POST" | "PATCH",
  path: string,
  body: unknown,
): Promise<T> {
  const token = getAdminToken();
  if (!token) throw new NoSessionError();

  const url = new URL(path, API_BASE_URL);
  const envelope = await withAuthRetry(token, async (t) =>
    fetchEnvelope<T>(url, {
      method,
      headers: {
        Authorization: `Bearer ${t}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }),
  );

  return envelope.data as T;
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiMutate<T>("POST", path, body);
}

/**
 * POST with no bearer token attached — for the login-flow endpoints
 * (`/auth/otp/request`, `/auth/otp/verify`, `/auth/mfa/verify`,
 * `src/lib/api/auth.ts`) and this file's own token refresh above,
 * which by definition run before a (valid) session token exists.
 * Every other endpoint in this app requires a real admin session and
 * must keep using `apiPost`/`apiGet`/`apiMutate` above, which attach
 * one and throw `NoSessionError` when there isn't one — this function
 * is the one deliberate exception, not a general-purpose
 * unauthenticated escape hatch.
 */
export async function authPost<T>(path: string, body: unknown): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  const envelope = await fetchEnvelope<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return envelope.data as T;
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiMutate<T>("PATCH", path, body);
}

/**
 * multipart/form-data POST (CSV Bulk Customer Targeting, api-contracts.md
 * §46.19) — the one upload this app makes. Deliberately does not set a
 * Content-Type header: the browser sets `multipart/form-data;
 * boundary=...` itself from the FormData body, and setting one manually
 * would omit the boundary and break parsing.
 */
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const token = getAdminToken();
  if (!token) throw new NoSessionError();

  const formData = new FormData();
  formData.append("file", file);

  const url = new URL(path, API_BASE_URL);
  const envelope = await withAuthRetry(token, async (t) =>
    fetchEnvelope<T>(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${t}` },
      body: formData,
    }),
  );

  return envelope.data as T;
}
