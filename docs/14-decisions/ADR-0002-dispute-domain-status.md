ADR-0002 — Status of "Dispute" as a Business Domain (Decision Required)

Status: Decision required — NOT decided by this record
Date recorded: 2026-08-20
Deciders: Unresolved. This ADR documents a discrepancy found during
documentation/architecture reconciliation; it does not choose an outcome.

1. Context

Several later, implementation-oriented documents describe a substantial
"Dispute" concept:

- docs/11-implementation/implementation-readiness.md §16 defines a full
  "Dispute Module" (owns: dispute creation, evidence submission, evidence
  deadline, admin review, admin decision, audit trail) as a peer to the
  Ride/Matching/Wallet/Payment/etc. modules; §61/§68 give "Disputes /
  Evidence / Admin / Audit" its own implementation phase (Phase 7) with a
  dedicated Definition-of-Done checklist; §48 lists "Dispute expiry" as a
  background worker job; §52 lists `disputes_total` and
  `admin_override_total` as core metrics.
- docs/08-security/security.md §11–§15 describes "Admin GPS Override," "GPS
  Dispute Security," and an evidence-submission workflow in detail.
- docs/10-testing/testing-strategy.md §20–§23 and §89–§90 build extensive
  test scenarios around GPS dispute creation, evidence windows, and admin
  APPROVE/REJECT decisions.

However, searching the canonical, upstream documents that are supposed to
establish domain boundaries before these downstream documents were written
finds only narrow, scattered mentions — never a formal "Dispute" domain:

- docs/01-product/PRD.md mentions "Dispute handling" exactly once, as a
  single bullet under the MVP "Core Platform" capability list (§56), with no
  elaboration anywhere else in the document.
- docs/02-business/business-rules.md BR-121 ("Ride Fare Disputes") states
  that "because ride fares may be paid directly to drivers, ride-fare
  disputes require a support/admin process" — explicitly routing disputes
  through the existing Support/Admin process rather than establishing a new
  domain.
- docs/03-architecture/technical-architecture.md's canonical 18-domain list
  (§4) has no "Dispute" domain. The only appearance of the word is
  "Dispute/review" in §33 ("Penalty Architecture"), listed as one benefit of
  having a dedicated penalties table (alongside "Expiry," "Payment status,"
  "Audit," "Wallet settlement") — i.e., the ability to dispute/review a
  penalty, not a domain of its own.
- docs/04-domain-design/domain-design.md's Domain Classification (§4) —
  which explicitly mirrors the architecture doc's domain list — likewise has
  no "Dispute" domain. The only appearance is a command named
  `DisputePenalty` inside the Penalty Domain's command list (§17.3,
  alongside `ApplyCustomerCancellationPenalty`, `RecordStrike`,
  `ExpirePenalty`, `ResolvePenalty`) — again, a capability for disputing a
  penalty, not a standalone domain.
- docs/04-database/database-design.md has no `dispute.*` schema. The 18
  logical schemas listed (§3) match the architecture/domain-design domain
  list exactly and do not include one for disputes.
- docs/05-api/api-contracts.md has no `/disputes` or `/rides/{id}/dispute`
  endpoints anywhere.
- docs/06-events/event-contracts.md has no `dispute.*` event family among
  the 15 listed Kafka topic families (§6) or the Initial Event Registry
  (§56).
- docs/07-state-machines/state-machines.md has no Dispute state machine and
  does not use the word "dispute" anywhere in its 1,424 lines.

2. What this establishes

Ride-fare disputes (BR-121) and penalty disputes (`DisputePenalty` command)
are acknowledged in the canonical documents, but only as a process routed
through existing Support/Admin/Penalty capabilities — never as a dedicated
domain with its own database schema, API surface, events, or state machine.

The GPS-verification-dispute workflow described at length in security.md and
testing-strategy.md (evidence upload, admin APPROVE/REJECT, GPS override) has
no origin anywhere in PRD → business-rules → technical-architecture →
domain-design → database-design → api-contracts → event-contracts →
state-machines. It appears to have been introduced directly in the security
and testing documents (and then formalized further in
implementation-readiness.md's "Dispute Module" and "Phase 7") without ever
passing through the domain/database/API/event/state-machine layers the
documentation set's own source-of-truth hierarchy requires
(business-rules.md §45: "PRD → Business Rules → Architecture → API Contracts
→ Database/Events/State Machines → Tests → Implement").

3. Classification

Per the four options considered:

A. An explicitly approved business domain — NOT supported by the evidence
   above; no canonical document establishes it as a domain.
B. An approved subdomain/capability — PARTIALLY supported: ride-fare
   disputes are an acknowledged Support/Admin capability (BR-121), and
   penalty disputes are an acknowledged Penalty-domain command
   (`DisputePenalty`). Neither of these covers the GPS-verification-dispute
   workflow (evidence upload, admin GPS override, 72-hour window) that
   security.md, testing-strategy.md, and implementation-readiness.md
   describe in detail.
C. An implementation concept that has not been formally established — BEST
   SUPPORTED classification for the GPS-dispute workflow specifically. It
   was built out in security/testing/implementation-readiness documentation
   without ever being ratified in the architecture → domain-design →
   database-design → api-contracts → event-contracts → state-machines chain.
D. Genuinely unresolved — the underlying question ("should GPS-verification
   disputes be their own domain, or a capability of Verification/Ride/
   Support?") has never been put to product/business for a decision.

4. Decision

NOT MADE. This ADR intentionally does not choose between routing GPS
disputes through the existing Verification domain, treating them as a Ride
sub-capability, formally establishing a new Dispute domain, or some other
structure. Doing so would invent a business/architecture decision that the
canonical documents never made — which this reconciliation task is
explicitly required not to do.

5. What must happen before Phase 7 (per implementation-readiness.md §61) is
   implemented

- Product/architecture must explicitly decide whether "Dispute" (specifically
  GPS-verification dispute handling) is its own domain, a capability of an
  existing domain (most plausibly Verification, given the GPS-verification
  subject matter, or Support/Admin, given BR-121's precedent), or deferred.
- Whichever domain owns it must be added to technical-architecture.md §4–5
  and docs/04-domain-design/domain-design.md §3–4's domain lists if a new
  domain is chosen, or explicitly assigned to an existing domain's
  responsibility list if not.
- database-design.md needs an owning schema (new `dispute.*` schema, or
  tables under the owning domain's existing schema).
- api-contracts.md needs the corresponding endpoints.
- event-contracts.md needs the corresponding event family.
- state-machines.md needs the corresponding state machine.
- Only after the above is implementation-readiness.md §16 ("Dispute
  Module")/§68 (Phase 7 Definition of Done) consistent with the rest of the
  documentation set's own governance rule.

6. Consequences of leaving this unresolved

If Phase 7 is implemented against implementation-readiness.md's "Dispute
Module" as currently written, the resulting code will have no corresponding
domain/database/API/event/state-machine documentation to be reviewed
against — reproducing, in code, the same gap this ADR documents in the
docs.
