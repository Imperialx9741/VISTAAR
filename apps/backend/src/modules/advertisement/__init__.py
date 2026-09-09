"""VISTAAR Advertisement module — Phase 17.

Owns `advertisement.campaigns`, `advertisement.driver_campaigns`, and
`advertisement.payouts`, per docs/04-database/database-design.md §31,
implementing domain-design.md §22.3's six commands (CreateCampaign,
AssignDriver, SubmitInstallationProof, VerifyAdvertisement,
CalculatePayout, SettlePayout).

See docs/14-decisions/ADR-0018-advertisement-domain-scope-and-open-
items.md for the full scope reasoning. This module deliberately does
NOT implement:

- Any HTTP endpoint. `api-contracts.md` documents zero Advertisement
  endpoints anywhere — no path, no request/response shape. Building one
  now would mean inventing a new public API contract (roadmap §0.3's
  explicit mandatory-stop condition), unlike every other module built
  so far, which had at least a documented endpoint to implement
  against.
- Admoto (or any) automated ad-verification integration.
  technical-architecture.md §55 names Admoto as the intended partner,
  but no requirement/candidate list/credential plan is documented
  anywhere (roadmap §0.4's required steps before integrating any
  external provider). `verify_advertisement()` is a manual admin
  decision instead — the same treatment this codebase already gives
  document verification everywhere else.
- Composing `WalletService.credit()` (ADVERTISEMENT_PAYOUT, already in
  the transaction-type enum) or outbox event publication
  (`advertisement.campaign_assigned`/`verified`/`payout_issued`,
  event-contracts.md §24) — both are the router/composition layer's
  job in this codebase's established architecture, and there is no
  router yet. `calculate_payout()`/`mark_payout_paid()` are split into
  two methods specifically so a future router can do that composition
  in between — see service.py's docstring and
  tests/test_advertisement_service.py's
  test_full_campaign_to_payout_flow_composes_with_wallet_credit for a
  worked example.

What it does do:

- `create_campaign()`: campaigns are immediately ACTIVE on creation
  (ADR-0018 Decision 2 — no draft/approval step is documented).
- `assign_driver()`: creates an ASSIGNED driver_campaigns row.
- `submit_installation_proof()`: driver-owned (IDOR-safe — same
  "not found" response for a missing or another driver's assignment),
  requires ASSIGNED status, transitions to PROOF_SUBMITTED +
  verification_status PENDING.
- `verify_advertisement()`: admin decision (approve/reject), requires
  PROOF_SUBMITTED, transitions to VERIFIED/REJECTED.
- `calculate_payout()`: requires VERIFIED, computes the gross/driver/
  vistaar split from the campaign's own percentages (domain-design.md
  §22.4's approved 80/20 default), idempotent per driver_campaign via
  `uq_payouts_driver_campaign` (a caller retrying this raises
  `PayoutAlreadyCalculatedError` rather than silently returning the
  existing row — recalculating is a caller error worth surfacing).
- `mark_payout_paid()`: records a payout as PAID and the driver_campaign
  as PAID — called only after the wallet credit itself has already
  happened elsewhere.

Layering mirrors modules/wallet/ and modules/penalty/:

    domain/         pure business logic — no FastAPI/SQLAlchemy imports
    ports.py        CampaignRepository, DriverCampaignRepository,
                    PayoutRepository Protocols
    models.py       SQLAlchemy ORM models for the three tables
    repositories.py SQLAlchemy-backed implementations of the ports above
    service.py      application service (use cases): AdvertisementService
    dependencies.py FastAPI DI wiring (no router consumes it yet)

No schemas.py, no router.py — see "deliberately does NOT implement"
above.
"""
