ADR-0051 — Admin MFA (TOTP Authenticator App)

Status: Accepted and implemented (2026-08-28) — owner decision ("Admin
MFA → TOTP authenticator app"), resolving the gap Phase 02/Phase 19's own
assessment repeatedly flagged: "TOTP is genuinely self-contained... but
no documented enrollment/verify endpoint shape exists anywhere — building
it now means inventing a new public API contract, its own §0.3
mandatory-stop condition, independent of the mechanism itself being
simple."

Date recorded: 2026-08-28.
Deciders: Project owner (explicit written decision, 2026-08-28).

1. Context

security.md/business-rules.md §43 name Admin MFA as a real requirement
but never specify a mechanism, an enrollment flow, or an endpoint shape.
ADR-0040 (Admin Permission Model) explicitly left this gap open. The
owner's decision supplies the mechanism (TOTP, RFC 6238 — a standard
authenticator app: Google Authenticator, Authy, 1Password, etc.) but not
the endpoint/flow design, which this ADR now specifies before writing
any code, per this codebase's own "a new public API contract needs the
same review any other new endpoint gets" rule.

2. Decision 1 — MFA is a generic identity-layer capability, not an
   admin-layer one

Building this inside `modules/admin/` would require `modules/identity/`
(which every account type's login already goes through) to import
`modules/admin/` to know whether to require a second factor — the
reverse of every existing composition direction in this codebase (Admin
composes Identity/Driver/Vehicle/etc., never the other way). Instead,
`modules/identity/` gains a generic "does this account have MFA
enabled" capability, usable by any account type, with enrollment
endpoints scoped to ADMIN accounts only (via `require_admin`) since
that's the only account type asked for today — not because the
mechanism is admin-specific. A customer/driver login is completely
unaffected: MFA only activates when an account has an ACTIVE
`identity.mfa_credentials` row, which nothing creates for a
customer/driver account.

3. Decision 2 — Schema

```
CREATE TABLE identity.mfa_credentials (
    account_id UUID PRIMARY KEY REFERENCES identity.accounts(id),
    secret VARCHAR(64) NOT NULL,   -- base32 TOTP secret
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING | ACTIVE
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);
```

The secret is stored as plain base32 text, not application-level
encrypted. No envelope-encryption/KMS infrastructure exists anywhere in
this codebase for any field (every other secret-shaped value — JWT
signing key, MSG91/S3 credentials — lives in environment configuration,
never a database column); building one now, for this one column, would
be new infrastructure well beyond "add MFA." Flagged explicitly, the
same class of disclosed scope trim ADR-0035 already made for
production-grade secret management ("development-complete... needs a
real domain/cloud provider for production form"). The database's own
access controls (never publicly reachable, TLS in transit, the same
trust boundary every other table in this schema already relies on) are
what protect it, same as everything else in Postgres today.

PENDING means "enrolled, not yet confirmed with a real code from the
app" — mirrors this codebase's own established Driver/Vehicle
verification-status shape (submit, then confirm/approve) rather than
activating on enrollment alone, which would let an admin lock themselves
out with a mistyped secret they never actually tested.

4. Decision 3 — Endpoints (new public API contract)

```
POST /api/v1/auth/mfa/enroll     (admin-only for now; any authenticated
                                   account technically eligible)
  -> generates a new PENDING secret, returns {secret, otpauth_uri} for
     client-side QR code rendering. Calling this again before confirming
     replaces the PENDING secret (no orphaned unconfirmed rows).

POST /api/v1/auth/mfa/confirm
  body: {code}
  -> verifies `code` against the PENDING secret; on success, flips it to
     ACTIVE. From this point, this account's OTP login requires a second
     step.

POST /api/v1/auth/mfa/verify
  body: {mfa_token, code}
  -> `mfa_token` is the short-lived (5 minute) pre-auth JWT
     `POST /api/v1/auth/otp/verify` now returns instead of real tokens
     when the account has an ACTIVE MFA credential. Verifies `code`
     against the ACTIVE secret; on success, issues the real
     access/refresh token pair exactly as `otp/verify` would have
     without MFA.

POST /api/v1/auth/mfa/disable
  body: {code}
  -> requires a valid current code (not just a bearer token) before
     turning MFA off — the same "prove you still have the second factor
     before removing it" pattern every real MFA implementation uses;
     deletes the credentials row.
```

`POST /api/v1/auth/otp/verify`'s response shape changes conditionally,
not unconditionally: an account with no MFA credential (every
customer/driver, and every admin who hasn't enrolled) gets the exact
same `{access_token, refresh_token, expires_in}` shape as today — zero
behavior change. An account with an ACTIVE MFA credential instead gets
`{mfa_required: true, mfa_token: "..."}` and must call
`POST /api/v1/auth/mfa/verify` next.

5. Decision 4 — Token purpose claim (security hardening this change
   requires)

The pre-auth `mfa_token` must not be usable as a real access token if
leaked or misapplied — `identity/security.py`'s `issue_access_token()`
gains a `"purpose": "access"` JWT claim (previously absent), and a
sibling `issue_mfa_pending_token()` issues `"purpose": "mfa_pending"`
instead. `get_current_account()` (the dependency every authenticated
route already goes through) now additionally rejects any token whose
`purpose` claim isn't `"access"` — a pre-auth token can only ever be
consumed by `POST /api/v1/auth/mfa/verify`, nothing else. Every real
access token issued anywhere in this codebase already flows through
`issue_access_token()`, so this is additive, not a breaking change to
any existing caller.

6. What this does NOT resolve

- Recovery codes / backup codes for a lost authenticator device — no
  source document asks for this; flagged as a real operational gap
  (today, a locked-out admin needs a Super Admin or direct DB access to
  clear their `identity.mfa_credentials` row), not silently solved.
- Enforcing MFA as mandatory for every admin — enrollment stays
  opt-in/self-service; making it mandatory for all Super Admins (or all
  admins) is a policy decision nobody has made.
- Any change to the customer/driver OTP login flow or its response shape
  for an account with no MFA credential — verified unchanged (Decision 4
  of the implementation report / test suite).
