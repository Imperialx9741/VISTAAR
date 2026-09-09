import { apiPost, authPost } from "./client";
import { getAdminRefreshToken } from "./session";

/**
 * Admin login (2026-09-08) — the same OTP flow every account type uses
 * (`modules/identity/router.py`, api-contracts.md §6-7), with
 * `account_type: "ADMIN"`, plus the conditional MFA step ADR-0051 adds
 * for any account with an ACTIVE `identity.mfa_credentials` row. There
 * is no separate "admin login" endpoint — an admin account is
 * provisioned by another admin first (`POST /api/v1/admin/admins`,
 * Admin Management), then signs in the same way a customer/driver
 * would, just with this `account_type`.
 */

interface OtpRequestResponse {
  challenge_id: string;
  expires_in: number;
}

interface TokenPairResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

interface MfaRequiredResponse {
  mfa_required: true;
  mfa_token: string;
  expires_in: number;
}

export interface OtpChallenge {
  challengeId: string;
  expiresIn: number;
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export interface MfaChallenge {
  mfaToken: string;
  expiresIn: number;
}

export type OtpVerifyResult =
  | { mfaRequired: false; tokens: TokenPair }
  | { mfaRequired: true; mfa: MfaChallenge };

/** POST /api/v1/auth/otp/request */
export async function requestAdminOtp(phone: string): Promise<OtpChallenge> {
  const data = await authPost<OtpRequestResponse>("/api/v1/auth/otp/request", {
    phone,
    account_type: "ADMIN",
  });
  return { challengeId: data.challenge_id, expiresIn: data.expires_in };
}

/** POST /api/v1/auth/otp/verify — response shape branches on whether
 * this account has an ACTIVE MFA credential (ADR-0051 Decision 4);
 * `mfa_required` is only ever present (and `true`) on the MFA branch,
 * never a `false` sent explicitly, so presence is what's checked. */
export async function verifyAdminOtp(
  challengeId: string,
  otp: string,
): Promise<OtpVerifyResult> {
  const data = await authPost<TokenPairResponse | MfaRequiredResponse>(
    "/api/v1/auth/otp/verify",
    { challenge_id: challengeId, otp },
  );
  if ("mfa_required" in data) {
    return {
      mfaRequired: true,
      mfa: { mfaToken: data.mfa_token, expiresIn: data.expires_in },
    };
  }
  return {
    mfaRequired: false,
    tokens: {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      expiresIn: data.expires_in,
    },
  };
}

/** POST /api/v1/auth/mfa/verify — second step, only reached when
 * [verifyAdminOtp] returned `mfaRequired: true`. */
export async function verifyAdminMfa(
  mfaToken: string,
  code: string,
): Promise<TokenPair> {
  const data = await authPost<TokenPairResponse>("/api/v1/auth/mfa/verify", {
    mfa_token: mfaToken,
    code,
  });
  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresIn: data.expires_in,
  };
}

/** POST /api/v1/auth/logout — best-effort; callers should clear the
 * local session (`clearAdminSession`) regardless of whether this
 * succeeds, since the whole point of signing out is that this browser
 * stops acting as that admin either way. */
export async function logoutAdmin(): Promise<void> {
  await apiPost("/api/v1/auth/logout", {
    refresh_token: getAdminRefreshToken(),
  });
}
