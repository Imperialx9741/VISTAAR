"use client";

import { useState, type FormEvent } from "react";
import {
  requestAdminOtp,
  verifyAdminMfa,
  verifyAdminOtp,
  type TokenPair,
} from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { setAdminSession } from "@/lib/api/session";
import styles from "./LoginPage.module.css";

type Step =
  | { kind: "phone" }
  | { kind: "otp"; phone: string; challengeId: string }
  | { kind: "mfa"; mfaToken: string };

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Check your connection and try again.";
}

/**
 * Admin sign-in (2026-09-08) — closes the gap `session.ts` used to
 * document directly: "no screen in this app writes vistaar_admin_token
 * yet." Same phone + OTP flow every account type goes through
 * (`account_type: "ADMIN"`), with a conditional third step for any
 * admin who has enrolled MFA (ADR-0051) — most admins won't see that
 * step at all, since enrollment is opt-in.
 *
 * Deliberately does NOT force every other page in this app behind a
 * hard redirect-to-login guard — that would be a separate, larger
 * change to this app's routing model. Every page already has its own
 * honest "no session yet, showing sample data" fallback
 * (`lib/api/dashboard.ts` and its siblings); this screen adds the real
 * way to get past that, it doesn't remove the fallback.
 */
export function LoginPage() {
  const [step, setStep] = useState<Step>({ kind: "phone" });
  const [phoneInput, setPhoneInput] = useState("");
  const [codeInput, setCodeInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function onSessionEstablished(tokens: TokenPair) {
    // Explicitly picks the two fields setAdminSession actually stores
    // rather than passing `tokens` straight through — `expiresIn`
    // isn't persisted anywhere today (session.ts's own doc comment:
    // there is no refresh-on-expiry interceptor yet), and this keeps
    // that an explicit, visible choice here rather than an implicit
    // side effect of TokenPair's shape.
    setAdminSession({
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
    });
    // A full navigation, not next/navigation's router — same
    // deliberate choice as TopBar's sign-out (see its own doc comment):
    // an auth boundary should reset every component's state, and every
    // page's own data-fetching effect (getDashboardSummary and its
    // siblings) picks up the new session on this fresh load rather than
    // needing to know a session just changed underneath it.
    window.location.href = "/";
  }

  async function handlePhoneSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const digits = phoneInput.trim();
    if (digits.length !== 10) {
      setError("Enter a valid 10-digit mobile number.");
      return;
    }
    setIsSubmitting(true);
    try {
      const challenge = await requestAdminOtp(`+91${digits}`);
      setStep({ kind: "otp", phone: `+91${digits}`, challengeId: challenge.challengeId });
      setCodeInput("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleOtpSubmit(event: FormEvent) {
    event.preventDefault();
    if (step.kind !== "otp") return;
    setError(null);
    if (codeInput.trim().length < 4) {
      setError("Enter the code you received.");
      return;
    }
    setIsSubmitting(true);
    try {
      const result = await verifyAdminOtp(step.challengeId, codeInput.trim());
      if (result.mfaRequired) {
        setStep({ kind: "mfa", mfaToken: result.mfa.mfaToken });
        setCodeInput("");
      } else {
        onSessionEstablished(result.tokens);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleMfaSubmit(event: FormEvent) {
    event.preventDefault();
    if (step.kind !== "mfa") return;
    setError(null);
    if (codeInput.trim().length !== 6) {
      setError("Enter the 6-digit code from your authenticator app.");
      return;
    }
    setIsSubmitting(true);
    try {
      const tokens = await verifyAdminMfa(step.mfaToken, codeInput.trim());
      onSessionEstablished(tokens);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.brand}>
          <div className={styles.brandMark} aria-hidden="true">
            V
          </div>
          <div>
            <div className={styles.brandName}>VISTAAR</div>
            <div className={styles.brandSub}>Admin Console</div>
          </div>
        </div>

        {step.kind === "phone" && (
          <form className={styles.form} onSubmit={handlePhoneSubmit}>
            <h1 className={styles.heading}>Sign in</h1>
            <p className={styles.subheading}>
              Enter your admin mobile number to get a one-time code.
            </p>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="phone">
                Mobile number
              </label>
              <div className={styles.phoneRow}>
                <span className={styles.phonePrefix}>+91</span>
                <input
                  id="phone"
                  className={styles.input}
                  type="tel"
                  inputMode="numeric"
                  autoFocus
                  maxLength={10}
                  placeholder="9876543210"
                  value={phoneInput}
                  onChange={(e) =>
                    setPhoneInput(e.target.value.replace(/\D/g, "").slice(0, 10))
                  }
                />
              </div>
            </div>
            {error && <div className={styles.errorBanner}>{error}</div>}
            <button
              type="submit"
              className={styles.primaryButton}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Sending…" : "Send code"}
            </button>
          </form>
        )}

        {step.kind === "otp" && (
          <form className={styles.form} onSubmit={handleOtpSubmit}>
            <h1 className={styles.heading}>Enter the code</h1>
            <p className={styles.subheading}>Sent to {step.phone}.</p>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="otp">
                One-time code
              </label>
              <input
                id="otp"
                className={styles.input}
                type="text"
                inputMode="numeric"
                autoFocus
                maxLength={6}
                placeholder="123456"
                value={codeInput}
                onChange={(e) =>
                  setCodeInput(e.target.value.replace(/\D/g, "").slice(0, 6))
                }
              />
            </div>
            {error && <div className={styles.errorBanner}>{error}</div>}
            <button
              type="submit"
              className={styles.primaryButton}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Verifying…" : "Verify"}
            </button>
            <button
              type="button"
              className={styles.linkButton}
              onClick={() => {
                setError(null);
                setCodeInput("");
                setStep({ kind: "phone" });
              }}
            >
              Use a different number
            </button>
          </form>
        )}

        {step.kind === "mfa" && (
          <form className={styles.form} onSubmit={handleMfaSubmit}>
            <h1 className={styles.heading}>Two-factor code</h1>
            <p className={styles.subheading}>
              Enter the 6-digit code from your authenticator app.
            </p>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="mfa">
                Authenticator code
              </label>
              <input
                id="mfa"
                className={styles.input}
                type="text"
                inputMode="numeric"
                autoFocus
                maxLength={6}
                placeholder="123456"
                value={codeInput}
                onChange={(e) =>
                  setCodeInput(e.target.value.replace(/\D/g, "").slice(0, 6))
                }
              />
            </div>
            {error && <div className={styles.errorBanner}>{error}</div>}
            <button
              type="submit"
              className={styles.primaryButton}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Verifying…" : "Verify"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
