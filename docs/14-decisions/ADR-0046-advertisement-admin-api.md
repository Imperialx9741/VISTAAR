ADR-0046 — Advertisement Admin API

Status: Accepted and implemented (2026-08-26) — owner decision #4 of the
2026-08-26 "approved product decisions" batch, recorded design-only per
the owner's "DO NOT IMPLEMENT RUNTIME CODE YET" instruction on that
batch, then implemented the same day under the owner's subsequent
broader authorization to build everything not blocked on an external
credential. Resolves ADR-0018 Item 2 ("The HTTP API contract: deferred,
not decided here") — Item 3 (Admoto integration) stays deferred,
unchanged by this ADR.

Date recorded: 2026-08-26.
Deciders: Project owner (explicit written decision, 2026-08-26).

1. Context

ADR-0018 built the full Advertisement domain/service/repository layer
(`CreateCampaign`, `AssignDriver`, `SubmitInstallationProof`,
`VerifyAdvertisement`, `CalculatePayout`, `SettlePayout`/
`mark_payout_paid`) with real test coverage, but deliberately built no
HTTP router — "no endpoint path or request/response shape is
documented anywhere... inventing one would be exactly the 'new public
API contract' §0.3 flags as a mandatory stop condition." The owner's
decision #4 is that missing product/API decision: campaign management,
campaign status, driver assignment, installation/proof review,
approve/reject proof, "Admoto verification status" (the already-built
*manual* `verification_status` field — real Admoto integration is
still Item 3, still deferred, see §10 of the decision batch:
"WhatsApp and Payment... provided separately," the same treatment this
ADR gives Admoto), and payout/settlement monitoring — preserving the
already-documented 80/20 split, no new ad economics.

Every command this ADR composes already exists and is already tested
(`tests/test_advertisement_service.py`); this ADR only adds the HTTP
surface and the list/search repository methods that surface needs — no
domain/service logic changes.

2. Decision 1 — Campaign status gains a real lifecycle: ACTIVE ⇄
   PAUSED → ENDED

`CampaignStatus` today has exactly one value, `ACTIVE` — ADR-0018
Decision 2 recorded that "nothing documents a draft/approval step
before that," which is still true and unchanged (a campaign is still
immediately usable at creation, no DRAFT/review gate is introduced).
But the owner's decision explicitly names "campaign status" as a
required admin capability, and an admin campaign-management screen
with no way to pause or end a campaign isn't real status management —
just a permanently-fixed label. Extended, mirroring the exact
Pause/End shape ADR-0041's own Campaign entity already uses:

```
ALTER TABLE advertisement.campaigns
    ALTER COLUMN status SET DEFAULT 'ACTIVE';
    -- status now: ACTIVE | PAUSED | ENDED
```

`ACTIVE ⇄ PAUSED` (an admin can pause and resume), `(ACTIVE or
PAUSED) → ENDED` (terminal). A PAUSED/ENDED campaign accepts no new
`AssignDriver` calls (`CampaignNotActiveError`, new) — existing
assignments already in flight (PROOF_SUBMITTED, VERIFIED, etc.) are
unaffected and can still be verified/paid out; pausing a campaign
stops new driver assignments, it does not strand drivers already
participating. `driver_campaigns.status`/`verification_status`/
`payouts.status` are untouched — ADR-0018 Decision 2's own state
machine for those was already complete for what "installation/proof
review," "approve/reject proof," and "payout/settlement monitoring"
need.

3. Decision 2 — "Admoto verification status" means exposing the
   existing manual field, not integrating Admoto

`driver_campaigns.verification_status` (PENDING | APPROVED | REJECTED)
already exists and is already set by the manual `verify_advertisement()`
admin decision ADR-0018 Decision 1 deliberately chose *instead of*
Admoto integration. The owner's decision list names this field, not a
live Admoto API call — read together with decision #10 of this same
batch ("Do not choose or implement a WhatsApp BSP or SBI payment
gateway... provided separately"), which gives Admoto (also named only
in technical-architecture.md's narrative, never confirmed selected —
ADR-0018 §5) the identical treatment. This ADR exposes
`verification_status` for admin read/decision through
`POST .../verify`; it does not touch Admoto credentials, onboarding,
or any external call, which remain exactly as deferred as ADR-0018
Item 3 left them.

4. Decision 3 — Repository methods this HTTP surface needs, none of
   which exist yet

```python
class CampaignRepository(Protocol):
    ...
    def save(self, campaign: Campaign) -> None: ...  # NEW — Pause/End writes back
    def list_all(self, *, status: str | None, offset: int, limit: int) -> tuple[list[Campaign], int]: ...  # NEW

class DriverCampaignRepository(Protocol):
    ...
    def search(self, *, campaign_id: uuid.UUID | None, driver_id: uuid.UUID | None,
               status: str | None, offset: int, limit: int) -> tuple[list[DriverCampaign], int]: ...  # NEW

class PayoutRepository(Protocol):
    ...
    def list_by_status(self, *, status: str | None, offset: int, limit: int) -> tuple[list[Payout], int]: ...  # NEW
```

`CampaignRepository.save()` is new because nothing has ever written
back to an existing campaign row before (Create was the only write) —
Pause/End need it. All four `list_all`/`search`/`list_by_status`
follow the exact `(items, total)` shape every other search method in
this codebase already uses.

5. Decision 4 — Admin endpoints

```
POST   /api/v1/admin/advertisements/campaigns                        Create Campaign
GET    /api/v1/admin/advertisements/campaigns?status=                 List/Search
GET    /api/v1/admin/advertisements/campaigns/{id}                    Get
POST   /api/v1/admin/advertisements/campaigns/{id}/pause              ACTIVE -> PAUSED
POST   /api/v1/admin/advertisements/campaigns/{id}/resume             PAUSED -> ACTIVE
POST   /api/v1/admin/advertisements/campaigns/{id}/end                -> ENDED (terminal)

POST   /api/v1/admin/advertisements/campaigns/{id}/assignments        Assign Driver
GET    /api/v1/admin/advertisements/assignments?campaign_id=&driver_id=&status=   Search (installation/proof review queue)
GET    /api/v1/admin/advertisements/assignments/{id}                  Get (incl. proof_uri, verification_status)
POST   /api/v1/admin/advertisements/assignments/{id}/verify           Approve/Reject proof ({"approved": true|false})

POST   /api/v1/admin/advertisements/assignments/{id}/payouts/calculate   CalculatePayout
GET    /api/v1/admin/advertisements/payouts?status=                   Payout/settlement monitoring
POST   /api/v1/admin/advertisements/payouts/{id}/settle                Composes WalletService.credit(ADVERTISEMENT_PAYOUT) then mark_payout_paid() — the exact sequence ADR-0018 §2's own worked-example test already demonstrates
```

New `AdminModule.ADVERTISEMENTS` permission is already in the catalog
(BR-126's 20-module list) but has never been used by any route —
this is its first consumer. `POST .../assignments` (driver-side
proof *submission*) stays a driver-facing endpoint, not built here —
this ADR is the admin surface only; a separate, still-undocumented
driver-facing `POST /api/v1/drivers/me/advertisements/{id}/proof`
remains exactly as unbuilt as before (ADR-0018 never scoped it and
this decision batch doesn't either). Every mutation audited.

6. What this does NOT resolve

- Admoto (or any) automated verification integration — ADR-0018 Item 3,
  explicitly still deferred (§10 of the owner's decision batch).
- A driver-facing "my campaigns"/proof-upload surface — not named in
  the owner's decision list (which is Admin Web-scoped), so not added.
- Any change to the 80/20 split or `payout_amount` semantics — "do not
  invent additional ad economics" (owner instruction) — `Campaign.new()`'s
  existing `driver_share_percent`/`vistaar_share_percent` parameters
  are exposed as-is on Create Campaign, not modified.
