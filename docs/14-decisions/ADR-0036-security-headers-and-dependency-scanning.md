ADR-0036 — Security Response Headers and CI Dependency Scanning

Status: Accepted.
Date recorded: 2026-08-25.
Deciders: Continuing autonomously under the owner's phase-level-autonomy
grant. No owner-level decision gate applies to either item below — see
Decision 1 for the one genuine engineering-judgment call this task made
and is recording here rather than guessing past silently.

1. Context

This task's very first exchange in this session (before any of the
other work recorded in ADR-0032 through ADR-0035) flagged two open
Phase 19 (Security) gaps: no security-response-headers middleware
anywhere in `apps/backend/src/main.py`, and no dependency-scanning step
in `.github/workflows/ci.yml`. Both remained unaddressed while larger,
owner-blocked-adjacent work took priority. Re-confirmed still open via
`grep` immediately before this task: no `X-Content-Type-Options`,
`Referrer-Policy`, `X-Frame-Options`, `Strict-Transport-Security`, or
`Content-Security-Policy` header is set anywhere, and no `pip-audit`/
`safety`/equivalent step exists in CI.

2. Decision 1 — Security headers, and the one real ambiguity in
   security.md §64: what CSP value to use

security.md §64 documents the expected header set explicitly:
Content-Security-Policy, X-Content-Type-Options, Referrer-Policy,
Strict-Transport-Security, and frame restrictions — but immediately
qualifies it: "Exact policy depends on the deployed frontend
architecture." Four of the five headers have an uncontroversial,
architecture-independent value (chosen below); the fifth, CSP, is where
that qualifier actually bites: FastAPI's default `/docs` (Swagger UI)
and `/redoc` pages load their own JS/CSS from a CDN
(`cdn.jsdelivr.net`), so a strict `default-src 'none'` CSP applied
everywhere would break those pages, and this backend serves JSON to a
Flutter mobile app and a Next.js admin-web app, neither of which is
"the deployed frontend architecture" a CSP header on *this* server's
responses is meant to protect (a CSP header only constrains what the
page that received it may load — for a JSON API response, that's every
consumer that isn't itself a browser rendering this server's HTML).
Resolved as engineering judgment, not a literal reading of any
document: apply a strict `Content-Security-Policy: default-src 'none';
frame-ancestors 'none'` to every response *except* the interactive-docs
paths (`/docs`, `/redoc`, `/openapi.json`), which are left without a
CSP header so they keep working locally and in any environment where
they're still exposed. Whether those paths should be disabled
(`docs_url=None`) in production at all is a separate decision this
task does not make — out of scope here, not asked, and orthogonal to
whether *this* header is safe to ship today.

The other four headers, applied to every response unconditionally:
- `X-Content-Type-Options: nosniff` — stops MIME-sniffing; no
  architecture dependency.
- `Referrer-Policy: strict-origin-when-cross-origin` — a conservative,
  widely-used default that leaks no path/query cross-origin.
- `X-Frame-Options: DENY` — covers security.md §64's "Frame
  restrictions" line; nothing this API serves should ever be framed.
- `Strict-Transport-Security: max-age=63072000; includeSubDomains` — a
  standard 2-year HSTS value; browsers ignore it entirely over plain
  HTTP (local dev), so it is safe to always send.

Implemented as `shared/security_headers.py`'s `SecurityHeadersMiddleware`
(Starlette `BaseHTTPMiddleware`), registered in `main.py` — the first
middleware in this codebase.

3. Decision 2 — `pip-audit` for CI dependency scanning, not a new
   vendor decision

Unlike the SMS/WhatsApp provider decisions this project's memory
explicitly reserves for the owner (a live account, credentials, an
ongoing vendor relationship, real cost implications), a dependency
scanner is a build-time dev tool in the same category as `ruff`/`mypy`,
already chosen without an ADR loop. `pip-audit` (PyPA's own tool,
queries the public PyPI Advisory Database, no account/API key/cost) is
added as a new CI step in `.github/workflows/ci.yml`'s existing
`backend-checks` job, run as a hard gate (a failing exit code fails the
job) — consistent with how this job already treats every other quality
check (format, lint, types, tests) as pass/fail, not advisory. If it
proves too noisy in practice (a transitive dependency with an unfixable
advisory), that is a future task's problem to triage with an explicit,
documented `--ignore-vuln` exception, not a reason to make the check
toothless from day one.

4. Consequences

- `main.py` gains its first `app.add_middleware(...)` call.
- `.github/workflows/ci.yml`'s `backend-checks` job gains a
  `pip-audit` step after the existing lint/type/test steps.
- No new API contract, no new external account, no new vendor —
  neither item needed to go back to the owner.
- Whether to disable `/docs`/`/redoc` in production, and whether a
  looser CSP should eventually cover them too, is left for a future
  task once the owner (or a documented decision) settles whether the
  interactive docs stay exposed in production at all.
