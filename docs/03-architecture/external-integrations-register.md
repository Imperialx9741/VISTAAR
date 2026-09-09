External Integrations Register

Status: Living register. Started 2026-08-21 alongside
[ADR-0008](../14-decisions/ADR-0008-verification-case-scope-and-open-items.md)
(Phase 2 / Task 2.6 — Verification & Compliance — Decision Resolution).
No external integration listed here has been selected or built — every
row below is a placeholder pending an explicit product/business decision.

Purpose: track every external service/provider VISTAAR's backend may
eventually depend on, so a provider decision, once made, has one place to
be recorded — not scattered across ADRs, code comments, and `.env.example`.
This register does not itself approve or select anything; it tracks
status.

How to read this table:

- Status: `Not selected` (no decision made yet) → `Selected — not yet
  integrated` (approved, pending implementation) → `Integrated` (live in
  code) → `Deprecated`/`Removed`.
- Credential columns are always placeholders (`TBD`) until a provider is
  actually selected and a credential is actually provisioned. This
  register never contains a real secret, key, or account identifier — see
  [security.md §48](../08-security/security.md) (secrets must never live
  in source code) and §89 (Open Security Configuration).
- "Decision Owner" is the role responsible for making the selection
  decision, not a person's name.

| Provider | Purpose | Phase | Credential Required | Credential Storage Location | Environment | Data Exchanged | Status | Decision Owner |
|---|---|---|---|---|---|---|---|---|
| TBD (driver document verification) | Authoritative check of driver Government ID / Driving Licence documents | Task 2.6+ | TBD | TBD (not yet provisioned) | TBD | Document evidence (`evidence_uri`), extracted fields | **Not selected** — pending explicit provider decision (business-rules.md §43 "Verification provider") | Product/Business |
| TBD (vehicle document verification) | Authoritative check of vehicle RC / Insurance documents | Task 2.6+ | TBD | TBD (not yet provisioned) | TBD | Document evidence (`evidence_uri`), extracted fields | **Not selected** — pending explicit provider decision (business-rules.md §43 "Verification provider") | Product/Business |
| TBD (OCR/AI document inspection) | Non-authoritative field extraction, image quality checks, possible-tampering signals | Task 2.6+ | TBD | TBD (not yet provisioned) | TBD | Document images / `evidence_uri` | **Not selected** — technical-architecture.md §6 documents `Groq/OpenAI-compatible LLM` for the Support/AI domain's conversational assistant; not confirmed as the intended provider for document OCR | Product/Engineering |

Existing (already-integrated) external dependencies, for reference — not
new entries requiring a decision, listed here only so this register is a
complete picture of what VISTAAR's backend actually talks to today:

| Provider | Purpose | Phase | Credential Required | Credential Storage Location | Environment | Data Exchanged | Status | Decision Owner |
|---|---|---|---|---|---|---|---|---|
| Dev console SMS adapter (`modules.identity.sms.DevConsoleSmsProvider`) | OTP delivery | Task 2.1 | None (dev-only, prints to console) | N/A | Development/test only | Phone number, OTP code | **Integrated** — dev-only stub, not a real SMS provider | Engineering |

Adding a row: when a provider is actually selected, update its Status to
`Selected — not yet integrated`, fill in the real Provider name and
Purpose, and record the credential *type* (not its value) plus its
intended storage location (e.g. `.env` / secrets manager — see
security.md §48). Move to `Integrated` only once the code exists and is
merged, referencing the implementing task.
