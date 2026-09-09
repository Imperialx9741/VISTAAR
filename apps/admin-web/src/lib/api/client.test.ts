import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getAdminToken: vi.fn(),
  getAdminRefreshToken: vi.fn(),
  setAdminSession: vi.fn(),
  clearAdminSession: vi.fn(),
}));

vi.mock("./session", () => ({
  getAdminToken: mocks.getAdminToken,
  getAdminRefreshToken: mocks.getAdminRefreshToken,
  setAdminSession: mocks.setAdminSession,
  clearAdminSession: mocks.clearAdminSession,
}));

/** Builds a standard envelope Response, matching api-contracts.md §3. */
function envelopeResponse(
  status: number,
  data: unknown,
  error: { code: string; message: string } | null = null,
) {
  return new Response(JSON.stringify({ data, error, request_id: "req_test" }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("client.ts — auto-refresh on AUTH_INVALID", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.getAdminToken.mockReturnValue("expired-access-token");
    mocks.getAdminRefreshToken.mockReturnValue("real-refresh-token");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("retries once with a fresh token after a single AUTH_INVALID, and stores the new session", async () => {
    const fetchMock = vi
      .fn()
      // First attempt: expired token rejected.
      .mockResolvedValueOnce(
        envelopeResponse(401, null, {
          code: "AUTH_INVALID",
          message: "expired",
        }),
      )
      // Refresh call succeeds.
      .mockResolvedValueOnce(
        envelopeResponse(200, {
          access_token: "new-access-token",
          refresh_token: "new-refresh-token",
          expires_in: 1800,
        }),
      )
      // Retried original request succeeds with the new token.
      .mockResolvedValueOnce(envelopeResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const { apiGet } = await import("./client");
    const result = await apiGet<{ ok: boolean }>("/api/v1/admin/me");

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    // The retried call used the new token, not the expired one.
    const retriedCallHeaders = fetchMock.mock.calls[2][1].headers as Record<
      string,
      string
    >;
    expect(retriedCallHeaders.Authorization).toBe("Bearer new-access-token");
    expect(mocks.setAdminSession).toHaveBeenCalledWith({
      accessToken: "new-access-token",
      refreshToken: "new-refresh-token",
    });
  });

  it("propagates the original AUTH_INVALID and clears the session when refresh itself fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        envelopeResponse(401, null, {
          code: "AUTH_INVALID",
          message: "expired",
        }),
      )
      .mockResolvedValueOnce(
        envelopeResponse(401, null, {
          code: "AUTH_INVALID",
          message: "refresh token also invalid",
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { apiGet } = await import("./client");

    await expect(apiGet("/api/v1/admin/me")).rejects.toMatchObject({
      code: "AUTH_INVALID",
      message: "expired",
    });
    expect(mocks.clearAdminSession).toHaveBeenCalled();
  });

  it("never retries AUTH_REQUIRED — nothing to refresh from a call with no token", async () => {
    mocks.getAdminToken.mockReturnValue("some-token");
    const fetchMock = vi.fn().mockResolvedValueOnce(
      envelopeResponse(401, null, {
        code: "AUTH_REQUIRED",
        message: "no token",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { apiGet } = await import("./client");

    await expect(apiGet("/api/v1/admin/me")).rejects.toMatchObject({
      code: "AUTH_REQUIRED",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shares one refresh call across concurrent AUTH_INVALID failures (single-flight)", async () => {
    let refreshCalls = 0;
    const fetchMock = vi
      .fn()
      .mockImplementation((url: string, init?: RequestInit) => {
        if (url.includes("/auth/refresh")) {
          refreshCalls += 1;
          return Promise.resolve(
            envelopeResponse(200, {
              access_token: "new-access-token",
              refresh_token: "new-refresh-token",
              expires_in: 1800,
            }),
          );
        }
        const headers = init?.headers as Record<string, string> | undefined;
        if (headers?.Authorization === "Bearer new-access-token") {
          return Promise.resolve(envelopeResponse(200, { ok: true }));
        }
        return Promise.resolve(
          envelopeResponse(401, null, { code: "AUTH_INVALID", message: "expired" }),
        );
      });
    vi.stubGlobal("fetch", fetchMock);

    const { apiGet } = await import("./client");
    const results = await Promise.all([
      apiGet("/api/v1/admin/me"),
      apiGet("/api/v1/admin/dashboard/summary"),
      apiGet("/api/v1/admin/audit-logs"),
    ]);

    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }]);
    expect(refreshCalls).toBe(1);
  });
});
