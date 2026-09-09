VISTAAR Admin Web — Implementation Plan

Status (2026-08-26, updated seven times that day; updated again
2026-08-28 and 2026-08-29): the backend API layer
for every module this plan originally marked "NEW — SCOPED" is
IMPLEMENTED — §4.1 Customers, §4.2 Drivers (incl. Suspend/Reactivate),
§4.3 Vehicles, §4.4 Verification, §4.7 Wallet Transaction History, §4.8
Fare Management (ADR-0042), §4.10 Offers/Coupons (ADR-0041), §4.11
Referrals search, §4.12 Notification History (only), §4.13 Safety,
§4.14 Support (Search/Detail/Resolve), §4.17 Audit Logs, §4.18 Admin
Management (ADR-0040), and §3 Dashboard (all but Online Drivers).

A second owner decision batch, the same day, approved product
decisions for most of what remained "NEEDS SCOPING" — recorded as new
ADRs, initially design only per an explicit owner instruction, then
given a broader "build everything you can without an external
credential" authorization the same day. §4.11's Referral Reward
Configuration (ADR-0043), §4.12's Notification Templates (ADR-0044),
§4.8's Platform Fee Management (ADR-0045), §4.15's Advertisements
(ADR-0046, resolving ADR-0018 Item 2), §4.16's Reports/Analytics
(ADR-0047), and, as of 2026-08-28, §4.19's Settings (ADR-0048) are now
IMPLEMENTED under that authorization — see api-contracts.md
§46.12/§46.13/§46.14/§46.15/§46.16/§46.17; Compose/Send Broadcast and
Audience Selection remained NEEDS SCOPING as of this batch (Templates
makes message *content* editable, it doesn't add ad hoc composition) —
both were separately scoped and built 2026-08-29 (ADR-0055 Tier C, see
§4.12 and §10 below); device-token registration was resolved the same
day too, ADR-0052, see below. A driver-facing proof-*submission* endpoint
remains unbuilt (ADR-0046 is the admin surface only). The rest are
still design only, no runtime code written yet: §4.9 Driver Strike
History (no ADR — pure read, same treatment as Audit Logs) and §4.10's
coupon CSV bulk customer targeting (ADR-0041 §9). See each ADR for the
full design and api-contracts.md §46.12-§46.19 for the endpoint
shapes.

The ADR-0011 Redis go_offline-cleanup gap blocking Dashboard's Online
Drivers figure (and the identical figure on §4.6/Reports) was fixed
2026-08-28 (`shared/geo.py`'s `remove_driver_location()` is now actually
called from `modules/driver/router.py`'s `go_offline` endpoint) — see
§3, corrected below. This closed out Dashboard's own last gap and
removed the technical blocker on §4.6 Matching/Offers' online-driver
count. §4.6 itself was then scoped and built 2026-08-29 (ADR-0054,
Tier C) — see §4.6 and §10 below.

Still genuinely NEEDS SCOPING, unaffected by any decision batch to
date: Admoto integration (ADR-0018 Item 3 — separate from the
now-resolved admin surface around it), WhatsApp BSP selection, and the
SBI payment gateway (the owner explicitly reserved these for a separate
decision). §4.12's own Compose/Send Broadcast + Audience Selection is
no longer on this list — resolved 2026-08-29, ADR-0055 Tier C (below).

Device-token registration itself is no longer NEEDS SCOPING: ADR-0052
(2026-08-28) implements `POST/DELETE /api/v1/notifications/me/devices`,
the `notification.device_tokens` table, and a `PushProvider` abstraction
(`DevConsolePushProvider` live today, `FcmPushProvider` coded but idle).
What remains open is a real Firebase project/service-account credential
— an external dependency, not a scoping gap. Compose/Send Broadcast +
Audience Selection, which ADR-0052 never touched, was itself resolved
separately the next day (ADR-0055 Tier C) — see §4.12 and §10 below.

Every existing and new admin route is permission-gated (ADR-0040). The
Admin Web *frontend* itself (this document's actual subject) — the
owner's original "DO NOT IMPLEMENT YET" instruction was about the
frontend specifically — started later, separately authorized: Dashboard
(§3) first, then §4.18 Admin Management, §4.1-§4.4
Customers/Drivers/Vehicles/Verification, §4.17 Audit Logs, §4.8 Fare
Management (incl. Platform Fee Management, 2026-08-29), §4.10
Offers/Coupons, §4.13/§4.14 Safety/Support, §4.12 Notifications
(history + templates), §4.11 Referrals (search + reward
configuration), §4.15 Advertisements (2026-08-29), §4.16
Reports/Analytics (2026-08-29), §4.19 Settings (2026-08-29), §4.5
Rides (2026-08-29), §4.7 Finance/Wallet (2026-08-29), §4.9
Penalties/Strikes (2026-08-29), and §4.6 Matching/Offers (ADR-0054,
2026-08-29) — all on 2026-08-28 except the nine named 2026-08-29
builds (see §10 for the build order and each section for detail).
Every module in the original 20-item catalog now has a real Admin Web
screen; building the backend API layer was itself a distinct,
separately-authorized task ("continue and complete the whole,"
2026-08-26), and designing (without implementing) the second decision
batch above was a further, separately-authorized task on top
of that.

Date recorded: 2026-08-26 (frontend status updated 2026-08-28 and
2026-08-29).

0. How to read this document

Every module section below states, explicitly, one of three things for
each screen: **EXISTS** (a real backend endpoint is already there to
build against), **NEW — SCOPED** (this plan specifies the exact new
endpoint needed, ready to build once approved), or **NEW — NEEDS
SCOPING** (the screen is named in the original spec but what it should
actually show/do isn't yet decided by any document — flagged rather
than invented). Nothing in this plan invents a business rule, a rate, or
a report definition; where the spec named a module without enough
detail to design a screen safely, that is called out, not guessed past.

1. Design System

1.1 Brand tokens

```
--vistaar-gold:        #EFBF04;   /* rgb(239, 191, 4)  */
--vistaar-deep-green:  #003314;   /* rgb(0, 51, 20)    */
```

Deep Green is the primary navigation/header color — the sidebar
background, the top app bar, and every "structural" surface. Gold is
the accent — active nav item, primary buttons/CTAs, focus rings, badge
highlights, and chart emphasis. Gold is never used as a large background
fill (a full-gold panel reads as a warning/alert, not a brand moment,
and fails contrast for white text) — it is a highlight color, applied to
small/medium elements against Deep Green or a neutral surface.

1.2 Supporting palette (derived, not specified by the owner — needs
sign-off same as any other visual choice, called out here rather than
silently decided)

A UI this dense (20 modules, tables, forms, status pills) needs more
than two colors to actually function — semantic states (success/
warning/danger/info) and neutrals for body text, borders, and card
surfaces. Proposed, all chosen to sit legibly alongside Gold/Deep Green
without competing with them as a second accent:

```
--surface:        #FFFFFF;   /* light theme card/page background */
--surface-dark:    #0A1F16;  /* dark theme card background, a Deep-Green-family tone */
--ink:             #16211C;  /* primary text, light theme — warm-black, green-biased */
--ink-dark:        #E7EFE9;  /* primary text, dark theme */
--ink-soft:        #5B6B62;  /* secondary text/labels */
--border:          rgba(0, 51, 20, 0.14);
--success:         #2E7D4F;  /* approvals, ACTIVE/SENT states — deliberately NOT the brand gold */
--warning:         #B8791A;  /* PENDING, expiring-soon states */
--danger:          #B23A2E;  /* REJECTED, SUSPENDED, FAILED states */
--info:            #2B6CB0;  /* informational badges, e.g. DRAFT */
```

Semantic colors are kept separate from the Gold/Deep Green brand pair
(a green "success" pill next to Deep Green chrome needs enough hue
separation to read as a different signal, not a brand accent) — this is
the one place this plan adds color the original spec didn't specify;
flagged for the owner to confirm or override, not treated as final.

1.3 Typography

No brand typeface was specified. Proposed: a system-first stack
(`-apple-system, "Segoe UI", Roboto, sans-serif`) for a dense
operations console — an operations table with hundreds of rows benefits
from a face users already read constantly, not a distinctive display
font competing for attention with the data. If VISTAAR has an existing
brand typeface used elsewhere (marketing site, mobile app), name it and
this plan uses it instead.

1.4 Component states

Every interactive element needs a visible focus state (security.md's
own general accessibility posture, and WCAG) — Gold at 3px, offset 2px,
on every focusable element, both themes. Disabled controls: 40%
opacity, no color change (never gray-out via changing the brand color
itself).

2. Navigation & Information Architecture

2.1 Sidebar structure

Deep Green background, Gold active-item indicator (left border + text
color), collapsed-by-default sub-items. Grouped, not a flat 20-item
list — a flat list this long is real navigation debt on day one:

```
DASHBOARD

OPERATIONS
  Rides
  Matching / Offers
  Safety / SOS
  Support / Disputes

PEOPLE
  Customers
  Drivers
  Vehicles
  Verification / Documents

MONEY
  Finance / Wallet
  Fare Management
  Penalties / Strikes
  Offers / Coupons
  Referrals

GROWTH
  Advertisements
  Notifications

INSIGHTS
  Reports / Analytics
  Audit Logs

SYSTEM
  Admin Management
  Settings
```

Every item's visibility is permission-gated per ADR-0040's module
catalog (§3 below) — an employee admin with no access to a module never
sees it in the sidebar at all, not just a disabled/greyed link. This is
UX convenience only; the actual enforcement is server-side
(`require_permission()`, ADR-0040 Decision 4) regardless of what the
sidebar shows.

2.2 Permission model applied to the UI

Each module maps 1:1 to `AdminModule` (ADR-0040). A page's own
mutating controls (Approve, Resolve, Create, Publish, Pause, Disable...)
render only when the current admin's access for that module is
`MANAGE`; read-only views render at `VIEW`. "Admin Management" and
"Settings" render only for a Super Admin — never for an employee admin
regardless of any permission row (ADR-0040's own rule).

The Admin Web reads its own admin's permission set once at login (a new
`GET /api/v1/admin/me` — see §12) and gates the sidebar/page controls
client-side from that; every actual mutation is re-checked server-side
regardless, so a stale client-side permission cache is a UX bug at
worst, never a security hole.

3. Dashboard

IMPLEMENTED (2026-08-26, backend — api-contracts.md §46.11; frontend
2026-08-28, `/`), including Online Drivers as of 2026-08-28 (corrected
below — the ADR-0011 Redis go_offline-cleanup gap that blocked it is
now fixed).

Widgets, each backed by a real number, not a placeholder:

| Widget | Source | Status |
| :--- | :--- | :--- |
| Today's rides (by status) | Count from Search Rides, filtered by `requested_at` today | EXISTS (client-side aggregation over existing endpoint, or...) |
| Pending driver approvals | Count of `verification_status = PENDING` | IMPLEMENTED |
| Pending vehicle approvals | Count of `verification_status = PENDING` | IMPLEMENTED |
| Online drivers | Redis `driver:online:*` count via `geo.count_online_drivers()` | IMPLEMENTED (corrected 2026-08-28: the ADR-0011 gap — a driver's Redis entry was never removed on go_offline, so a raw count would have overcounted indefinitely — is fixed; `modules/driver/router.py`'s `go_offline` endpoint now calls `geo.remove_driver_location()`, so the count is real and accurate; rendered on `/` as a StatCard) |
| Open GPS disputes | Search Disputes, `status=OPEN` | EXISTS |
| Open SOS incidents | `safety.incidents`, unresolved | IMPLEMENTED (Safety's admin read surface, §46.8, was built the same day) |
| Open support cases | `support.cases`, unresolved | IMPLEMENTED (Support's admin read surface, §46.9, was built the same day) |
| Outstanding penalties | Search Penalties, `status=OUTSTANDING` | EXISTS |
| Platform fee collected (today) | Sum of `wallet.transactions` where `type=PLATFORM_FEE`, today | IMPLEMENTED |

Recommendation (implemented as proposed): one aggregate endpoint,
`GET /api/v1/admin/dashboard/summary`, computing all of the above
server-side in one round trip, rather than the Admin Web firing several
separate requests on every dashboard load — cheaper, and the "online
drivers" figure specifically would need backend (Redis) access the
frontend has no business reaching directly, if it's ever built.

4. Module-by-module plan

Each module: screens, the API each screen needs, and the permission key
it's gated behind. "Existing" endpoints are cited by their real path;
"New" endpoints are this plan's proposed shape, not yet built or
API-contracts.md-documented — every one of them is a genuine new public
API contract (the same §0.3 gate this backend has stopped for
repeatedly) and needs the same review before implementation that any
other new endpoint in this codebase gets, not a blanket exemption just
because it's "for the Admin Web."

4.1 Customers — permission key `CUSTOMERS`

IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 — `/customers`,
`/customers/{id}`; see api-contracts.md §46.4).

| Screen | API | Status |
| :--- | :--- | :--- |
| Search/list customers | `GET /api/v1/admin/customers?query=&page=` | IMPLEMENTED |
| Customer detail (profile, ride history) | `GET /api/v1/admin/customers/{id}` (profile) + `GET /api/v1/admin/rides?customer_id=` (EXISTS, reused) | IMPLEMENTED (detail) / EXISTS (ride history — no Rides screen built yet, so the frontend doesn't link to it) |

No admin read surface over `customer.customers` existed before this —
only the customer's own self-service `GET /api/v1/customers/me`.

4.2 Drivers — permission key `DRIVERS`

IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 — `/drivers`,
`/drivers/{id}`; see api-contracts.md §46.4).

| Screen | API | Status |
| :--- | :--- | :--- |
| Search/list drivers | `GET /api/v1/admin/drivers?query=&status=&page=` | IMPLEMENTED |
| Driver Review (detail, documents, verification cases) | `GET /api/v1/admin/drivers/{id}` | IMPLEMENTED |
| Approve / Reject | `POST .../approve`, `POST .../reject` | IMPLEMENTED |
| Suspend / Reactivate | `POST /api/v1/admin/drivers/{id}/suspend`, `.../reactivate` | IMPLEMENTED (composed `DriverService.suspend_driver()`/`reactivate_driver()`, already built and tested at the service layer, ADR-0021 — only the HTTP route was missing) |

4.3 Vehicles — permission key `VEHICLES`

IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 — `/vehicles`,
`/vehicles/{id}`; see api-contracts.md §46.4).

| Screen | API | Status |
| :--- | :--- | :--- |
| Search/list vehicles | `GET /api/v1/admin/vehicles?query=&status=&page=` | IMPLEMENTED |
| Vehicle detail | `GET /api/v1/admin/vehicles/{id}` | IMPLEMENTED |
| Approve / Reject | `POST .../approve`, `POST .../reject` | IMPLEMENTED |

4.4 Verification / Documents — permission key `VERIFICATION`

IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 — `/verification`;
see api-contracts.md §46.4).

| Screen | API | Status |
| :--- | :--- | :--- |
| Pending-review queue (driver + vehicle documents) | `GET /api/v1/admin/verification/queue` | IMPLEMENTED — read-only; `subject_id` is the underlying document's own id, not a driver_id/vehicle_id, so the queue doesn't deep-link anywhere (no endpoint resolves one back to the other) |
| Vehicle document list | `GET /api/v1/admin/vehicles/{id}/documents` | IMPLEMENTED — surfaced on the Vehicle detail screen (§4.3), not its own route |

Driver documents are already visible nested inside Driver Review
(§4.2); vehicle documents had no admin visibility anywhere before this.

4.5 Rides — permission key `RIDES`

| Screen | API | Status |
| :--- | :--- | :--- |
| Search/list rides | `GET /api/v1/admin/rides` | IMPLEMENTED (frontend 2026-08-29 — `/rides`) |
| Ride detail (full lifecycle timeline, fare) | `GET /api/v1/admin/rides/{id}` | IMPLEMENTED (frontend 2026-08-29 — `/rides/{id}`) |

No new backend was needed for viewing — this section's backend was
always fully covered, it simply never got a numbered slot in §10's own
build order (a gap in the plan's own sequencing, corrected 2026-08-29).
No admin-side ride *intervention* action (force-cancel, reassign)
exists or was asked for; not included here — this screen never
mutates anything.

4.6 Matching / Offers — permission key `MATCHING`

IMPLEMENTED (ADR-0054, 2026-08-29 — Tier C of that ADR's own scoping
report, owner-chosen; frontend same day — `/matching`,
`/matching/{offerId}`). The last module in the 20-module catalog to
get one. No live driver-location map — explicitly excluded by the
owner's decision and left for a separate future ADR (§5 of ADR-0054).

| Screen | API | Status |
| :--- | :--- | :--- |
| Online-driver count, total and by category | `GET /api/v1/admin/matching/online-drivers` | IMPLEMENTED — real since the ADR-0011 go_offline-cleanup fix, keyed by the real matching_category_key() values (BIKE/AUTO/CAB:ECO/CAB:PREMIUM/CAB:PREMIUM_PLUS), not a coarser grouping |
| Search offers (status/ride/driver/date filters) | `GET /api/v1/admin/matching/offers?status=&ride_id=&driver_id=&from=&to=` | IMPLEMENTED — new `OfferRepository.search()`, no default date range (this is a search screen, not a report) |
| Offer detail | `GET /api/v1/admin/matching/offers/{id}` | IMPLEMENTED — admin-only, no driver-ownership restriction, same split Get Ride already has |

Documented/safe fields only (database-design.md §10.1) — no
coordinates, no Redis-derived location or availability data. See
api-contracts.md §46.20 and ADR-0054 for the full design.

4.7 Finance / Wallet — permission key `FINANCE`

| Screen | API | Status |
| :--- | :--- | :--- |
| Driver wallet balance | `GET /api/v1/admin/wallets/{driver_id}` | IMPLEMENTED (frontend 2026-08-29 — `/finance`, `/finance/{driverId}`) |
| Wallet transaction history | `GET /api/v1/admin/wallets/{driver_id}/transactions` | IMPLEMENTED (backend 2026-08-26 — the driver-facing equivalent, `GET /api/v1/drivers/me/wallet/transactions`, turned out to already exist, Phase 11/ADR-0024, built after this plan section was first written; both share `WalletService.list_transactions()`; frontend 2026-08-29, same routes as above) |

No search-all-wallets endpoint exists by design (a wallet is looked up
by a known driver_id, not browsed) — `/finance` is a driver-ID lookup
that navigates straight to `/finance/{driverId}`, rather than a list
screen with nothing to list.

4.8 Fare Management — permission key `FARE_MANAGEMENT`

IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 — `/fare-
management`, `/fare-management/{id}`; ADR-0042, api-contracts.md
§46.7). Vehicle category is a picker over the 5 real values
`calculate_fare()` actually keys off — `BIKE`/`AUTO`/`CAB_ECO`/
`CAB_PREMIUM`/`CAB_PREMIUM_PLUS` (modules/pricing/__init__.py) — not the
3-value `VehicleCategory` enum Drivers/Vehicles use; Publish's optional
`effective_from` is a `datetime-local` input, sent as ISO 8601 only when
filled in (omitted means "effective now," the backend's own default,
not client-supplied). `pricing.fare_rules.active` was replaced with
`status VARCHAR(20)
NOT NULL DEFAULT 'DRAFT'` (`DRAFT | IN_REVIEW | PUBLISHED`) exactly as
proposed below — see the ADR for the migration/backfill and the
Publish-closes-out-the-prior-rule mechanics.

Proposed addition (as built): `pricing.fare_rules.status VARCHAR(20)
NOT NULL DEFAULT 'DRAFT'` (`DRAFT | IN_REVIEW | PUBLISHED`), replacing
bare `active` as the workflow driver (`active` is now derived:
`PUBLISHED AND effective_from <= now() AND (effective_until IS NULL OR
effective_until > now())`, not stored independently).

| Screen | API | Status |
| :--- | :--- | :--- |
| List fare rules (by vehicle category, with version history) | `GET /api/v1/admin/fare-rules?vehicle_category=` | IMPLEMENTED (frontend: `/fare-management`) |
| Create draft | `POST /api/v1/admin/fare-rules` (status=DRAFT) | IMPLEMENTED (frontend: inline form on `/fare-management`) |
| Submit for review | `POST /api/v1/admin/fare-rules/{id}/submit-for-review` | IMPLEMENTED (frontend: `/fare-management/{id}`) |
| Publish (sets `effective_from`, status=PUBLISHED) | `POST /api/v1/admin/fare-rules/{id}/publish` | IMPLEMENTED (frontend: `/fare-management/{id}`) |
| Platform fee (was a hardcoded dict, `matching/router.py` — now a last-resort fallback only) | `pricing.platform_fee_rules` — own table/endpoint family, `FINANCE` permission | IMPLEMENTED (ADR-0045, 2026-08-26, backend; frontend 2026-08-28, §10 item (10) — `/fare-management/platform-fee`, `/fare-management/platform-fee/{id}`, identical DRAFT/IN_REVIEW/PUBLISHED workflow as this table's own rows above, reached via a link from `/fare-management`; see api-contracts.md §46.14) |

"Free waiting" (a grace period before waiting charges apply) has no
column anywhere — would be a new `fare_rules.free_waiting_minutes`
field, additive, not blocking the rest of this module.

4.9 Penalties / Strikes — permission key `PENALTIES`

| Screen | API | Status |
| :--- | :--- | :--- |
| Search/list penalties | `GET /api/v1/admin/penalties` | IMPLEMENTED (frontend 2026-08-29 — `/penalties`) |
| Resolve (waive) penalty | `POST /api/v1/admin/penalties/{id}/resolve` | IMPLEMENTED (frontend 2026-08-29 — inline in the `/penalties` row, an optional reason then Confirm waive) |
| Driver strike history | `GET /api/v1/admin/drivers/{id}/strikes` | IMPLEMENTED (backend + frontend 2026-08-29 — new `StrikeRepository.list_for_driver()`, reuses the DRIVERS permission, not a new module; frontend at `/drivers/{driverId}/strikes`, linked via a "View history →" link next to the strikes count already shown on `/drivers/{id}`; see api-contracts.md §46.18) |

4.10 Offers / Coupons — permission key `OFFERS_COUPONS`

Per ADR-0041 — IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 —
`/offers-coupons`, `/offers-coupons/{id}`).

| Screen | API | Status |
| :--- | :--- | :--- |
| List/search campaigns | `GET /api/v1/admin/campaigns` | IMPLEMENTED (ADR-0041) |
| Create campaign (DRAFT) | `POST /api/v1/admin/campaigns` | IMPLEMENTED |
| Edit (DRAFT only) | `PATCH /api/v1/admin/campaigns/{id}` | IMPLEMENTED — frontend reuses the same 13-field form for Create and Edit; the detail screen only ever shows the Edit action while `status=DRAFT`, matching the backend's own INVALID_STATE_TRANSITION otherwise |
| Activate / Pause / End | `POST .../activate`, `.../pause`, `.../end` | IMPLEMENTED |
| Eligible-customer list (when `eligible_scope=SELECTED`) | `eligible_customer_ids` in the create/edit body | IMPLEMENTED — the frontend's own answer to the upload/entry UX question this row already flagged as open: a plain textarea, one ID per line or comma-separated, parsed client-side into the same UUID list the API always took. Not a customer picker/search — no such component exists elsewhere in this app to reuse. |
| Bulk targeting via CSV upload | `POST /api/v1/admin/campaigns/{id}/eligible-customers/bulk` | IMPLEMENTED (backend + frontend 2026-08-29 — additive to the existing selected-customer set, not a replacement, see ADR-0041 §9/api-contracts.md §46.19; frontend: a file input + Upload button on `/offers-coupons/{id}`, shown only while DRAFT and eligible_scope='SELECTED', reporting added/already_eligible/unmatched back inline — the textarea above remains the entry method for `eligible_customer_ids` on Create/Edit, this is the separate additive bulk path) |

4.11 Referrals — permission key `REFERRALS`

| Screen | API | Status |
| :--- | :--- | :--- |
| Search/list referrals (with status, reward) | `GET /api/v1/admin/referrals` | IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 — `/referrals`; each row's own reward(s) shown inline, not a separate drill-down) |
| Referral reward configuration (was hardcoded ₹100/₹100 driver bonus, `admin/router.py`; 50%/3/2-use customer promotion grants, `modules/promotion/domain/entities.py` — the old constants remain only as a last-resort fallback if no PUBLISHED row exists) | `POST/GET /api/v1/admin/referral-config/driver-bonus[/{id}]`, `.../customer-rewards[/{id}]` | IMPLEMENTED (backend ADR-0043/2026-08-26, frontend 2026-08-28 — `/referrals/rewards` hosts both independent streams — Driver Referral Bonus and Customer Referral Rewards — each with its own inline create form, status filter, and detail route (`/referrals/rewards/driver-bonus/{id}`, `.../customer/{id}`) for Submit-for-Review/Publish; versioned/effective-dated, DRAFT/IN_REVIEW/PUBLISHED, future qualifications only, historical rewards frozen; see api-contracts.md §46.12) |

4.12 Notifications — permission key `NOTIFICATIONS`

Originally the largest cross-cutting gap — `NotificationService`
(ADR-0034) had no HTTP endpoint anywhere by design (§0.3), and Push
had no device-token source anywhere (ADR-0034 Decision 2). Every row
below is now IMPLEMENTED: history and templates landed 2026-08-26/
2026-08-28; Compose/Send Broadcast, Schedule a broadcast, and Audience
selection — the plan's last three open rows anywhere — were scoped and
built 2026-08-29 (ADR-0055, Tier C).

| Screen | API | Status |
| :--- | :--- | :--- |
| Compose/send broadcast | `POST /api/v1/admin/notifications/broadcasts` | IMPLEMENTED (backend + frontend 2026-08-29, ADR-0055 Tier C — `/notifications/broadcasts`. A broadcast's free-text subject/body is published under the hood as a one-off, broadcast-only `notification.templates` row (`event_key=NULL`, exactly the case ADR-0044's own schema comment anticipated), so every recipient's send still goes through `NotificationService.send()`'s existing content-resolution path unchanged; see api-contracts.md §46.21) |
| Schedule a broadcast | same endpoint + `scheduled_at`, dispatched by a new Celery Beat task polling every 5 minutes (ADR-0039's foundation, reused) | IMPLEMENTED (ADR-0055 — a future `scheduled_at` leaves the broadcast `SCHEDULED`; the audience is resolved fresh at actual dispatch time, never snapshotted at compose time) |
| Audience selection (all customers / all drivers / online drivers / selected users/group) | resolved server-side per audience type at send time | IMPLEMENTED (ADR-0055 — new `CustomerService.list_all_customer_ids()`, `DriverService.list_all_driver_ids()`, `geo.list_online_driver_ids()`; SELECTED reuses the same freeform-textarea-of-ids precedent Offers/Coupons' own `eligible_customer_ids` established) |
| Templates | `POST/GET /api/v1/admin/notifications/templates[/{id}]`, `.../publish` | IMPLEMENTED (backend ADR-0044/2026-08-26, frontend 2026-08-28 — `/notifications/templates`, `/notifications/templates/{id}`; `notification.templates`, draft/publish, per-(template_key, channel) version history, `notification.deliveries` gains `template_version_id` so history stays immutable; see api-contracts.md §46.13). Reused, not superseded, by Compose/Send Broadcast above — a broadcast publishes its own one-off template internally rather than requiring the admin to pre-create one |
| Notification history / delivery status | `GET /api/v1/admin/notifications/deliveries` (reads `notification.deliveries`, which already exists and is populated — ADR-0034/ADR-0038) | IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 — `/notifications`) — the table already had the data; only the admin read endpoint was missing |
| Device-token registration (mobile → backend) | `POST/DELETE /api/v1/notifications/me/devices` (one generic, identity-agnostic endpoint — not split per account type) | IMPLEMENTED (ADR-0052, 2026-08-28 — `notification.device_tokens` table, `PushProvider` abstraction; `NotificationService.send()`'s PUSH branch no longer unconditionally raises. What this does NOT resolve: a real Firebase project/service-account credential — `PUSH_PROVIDER` stays `dev` until the owner supplies one, an external dependency, not a code gap. No admin-facing frontend for this row — it's a device→backend contract, not an admin screen) |

4.13 Safety / SOS — permission key `SAFETY`

IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 — `/safety`,
`/safety/{id}`; api-contracts.md §46.8).

| Screen | API | Status |
| :--- | :--- | :--- |
| Incident queue (open SOS) | `GET /api/v1/admin/safety/incidents?status=` | IMPLEMENTED (composed `SafetyService`'s existing `acknowledge_incident`/`escalate_incident`/`resolve_incident`, already built and tested — same "service exists, no route" gap as Driver Suspension) |
| Incident detail | `GET /api/v1/admin/safety/incidents/{id}` | IMPLEMENTED |
| Acknowledge / Escalate / Resolve | `POST .../acknowledge`, `.../escalate`, `.../resolve` | IMPLEMENTED — the frontend only ever shows the one action the incident's current status actually allows (OPEN→Acknowledge, ACKNOWLEDGED→Escalate, IN_PROGRESS→Resolve), matching state-machines.md §45's linear lifecycle rather than offering all three always |

4.14 Support / Disputes — permission key `SUPPORT`

IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 for Search/Detail/
Resolve — `/support`, `/support/{id}`; api-contracts.md §46.9).

| Screen | API | Status |
| :--- | :--- | :--- |
| Search/list all support cases | `GET /api/v1/admin/support/cases?status=` | IMPLEMENTED |
| Case detail | `GET /api/v1/admin/support/cases/{id}` | IMPLEMENTED (distinct from the existing owner-only `GET /cases/{id}`, which an admin using their own admin_id would fail the IDOR ownership check against; frontend renders the full `messages` conversation, not just the case fields) |
| Resolve/close case | `POST /api/v1/admin/support/cases/{id}/resolve` | IMPLEMENTED — turned out `SupportService.resolve_case()` already existed (ADR-0022), resolving this row's own "NEEDS SCOPING" concern; only the HTTP route was missing |
| GPS Dispute queue/resolve (a specific dispute type) | `GET /api/v1/admin/gps-disputes`, `GET .../gps-disputes/{id}` (new, 2026-08-29), `POST .../resolve` | IMPLEMENTED (frontend 2026-08-29 — `/support/gps-disputes`, `/support/gps-disputes/{id}`, reached via a link from `/support`, same SUPPORT permission). The detail endpoint was a "service exists, no HTTP route" gap — `RideService.get_gps_dispute()` already existed, already tested, and its own docstring already named modules/admin/router.py as where the admin-facing composition belonged; only the route itself was missing, same pattern Safety's own Acknowledge/Escalate/Resolve routes hit earlier this project |

Not built: "Assign case" — `SupportService.assign_case()` also already
exists, but no source document names an Admin Web screen for it (this
table's own four rows are the complete §4.14 scope).

4.15 Advertisements — permission key `ADVERTISEMENTS`

Full domain/service layer existed and was tested (ADR-0018); zero HTTP
existed, by the same deliberate §0.3 restraint as Notification, purely
for want of an approved endpoint shape. IMPLEMENTED (backend ADR-0046,
2026-08-26 — owner decision #4 supplied exactly that shape; frontend
2026-08-29, §10 item (11) — `/advertisements`, `/advertisements/{id}`,
`/advertisements/assignments[/{id}]`, `/advertisements/payouts`). No
domain/service logic changes — only the HTTP surface, list/search
repository methods, and one new campaign-status lifecycle (ACTIVE was
the only value; PAUSED/ENDED are added since "campaign status" is a
named requirement).

| Screen | API | Status |
| :--- | :--- | :--- |
| Campaign list/detail | `GET /api/v1/admin/advertisements/campaigns[/{id}]?status=` | IMPLEMENTED |
| Create campaign | `POST /api/v1/admin/advertisements/campaigns` | IMPLEMENTED (always starts ACTIVE, unchanged) |
| Campaign status (pause/resume/end) | `POST .../campaigns/{id}/pause`, `.../resume`, `.../end` | IMPLEMENTED (new lifecycle, ADR-0046 Decision 1) |
| Driver assignment | `POST /api/v1/admin/advertisements/campaigns/{id}/assignments` | IMPLEMENTED (composes existing `AssignDriver`; rejected with `INVALID_STATE_TRANSITION` against a PAUSED/ENDED campaign) |
| Installation/proof review queue | `GET /api/v1/admin/advertisements/assignments?campaign_id=&driver_id=&status=` | IMPLEMENTED |
| Approve/reject proof (incl. "Admoto verification status") | `POST /api/v1/admin/advertisements/assignments/{id}/verify` | IMPLEMENTED (exposes the existing *manual* `verification_status` field, ADR-0018 Decision 1 — real Admoto integration, ADR-0018 Item 3, stays deferred) |
| Payout/settlement monitoring | `GET /api/v1/admin/advertisements/payouts?status=`, `POST .../calculate`, `.../settle` | IMPLEMENTED (composes existing `CalculatePayout`/`WalletService.credit()`/`mark_payout_paid()` — the exact sequence ADR-0018's own worked-example test already demonstrates) |

The documented 80%/20% driver/VISTAAR split (§4 header, ADR-0018) is
unchanged — exposed as Create Campaign parameters, not altered. See
api-contracts.md §46.15.

4.16 Reports / Analytics — permission key `REPORTS`

No domain existed at all — not a partial gap, a from-scratch module.
IMPLEMENTED (backend ADR-0047, 2026-08-26 — owner decision #5 supplied
the exact report list; frontend 2026-08-29, §10 item (12) — `/reports`,
one page hosting all nine, not nine separate routes). Nine fixed-shape
aggregate report endpoints, each over existing data with an optional
date range — not a generic query builder, not a separate data
warehouse:

| Screen | API | Status |
| :--- | :--- | :--- |
| Rides | `GET /api/v1/admin/reports/rides?from=&to=` | IMPLEMENTED |
| Customers | `GET /api/v1/admin/reports/customers?from=&to=` | IMPLEMENTED |
| Drivers | `GET /api/v1/admin/reports/drivers?from=&to=` | IMPLEMENTED |
| Financial/wallet activity | `GET /api/v1/admin/reports/financial?from=&to=` | IMPLEMENTED |
| Penalties | `GET /api/v1/admin/reports/penalties?from=&to=` | IMPLEMENTED |
| Promotions/referrals | `GET /api/v1/admin/reports/promotions-referrals?from=&to=` | IMPLEMENTED |
| Safety/support | `GET /api/v1/admin/reports/safety-support?from=&to=` | IMPLEMENTED |
| Notification delivery | `GET /api/v1/admin/reports/notifications?from=&to=` | IMPLEMENTED |
| Matching/operational | `GET /api/v1/admin/reports/matching?from=&to=` | IMPLEMENTED (still excludes "online drivers" as of 2026-08-29 — but the ADR-0011 Redis-staleness reason originally given no longer holds, that gap was fixed the same day Dashboard's own online-drivers figure was corrected, see §3; this endpoint simply hasn't been extended to add the field, a small follow-up if a matching-specific view of it is wanted) |

See api-contracts.md §46.16 and ADR-0047 for each report's exact field
shape.

4.17 Audit Logs — permission key `AUDIT_LOGS`

| Screen | API | Status |
| :--- | :--- | :--- |
| Search/filter audit log (by admin, action, target, date range) | `GET /api/v1/admin/audit-logs` | IMPLEMENTED (backend 2026-08-26, frontend 2026-08-28 — `/audit-logs`) |

`admin.audit_logs` was already written to on every privileged mutation
(confirmed across every existing admin route) — this module was a read
endpoint over data that already existed, the cheapest gap in this
entire plan, closed with no schema change (api-contracts.md §46.3).

4.18 Admin Management — permission key: none (Super Admin only, never
grantable — ADR-0040)

IMPLEMENTED (2026-08-28) — full backend (2026-08-26) plus the Admin Web
screen (2026-08-28). Backend: `POST/GET /api/v1/admin/admins`, `GET
.../admins/{id}`, `PATCH .../permissions`, `POST .../disable`, `POST
.../enable`, `GET /api/v1/admin/me` (api-contracts.md §46.1). Every
existing admin route (Drivers, Vehicles, Rides, Finance, Penalties,
Support/GPS-disputes) is permission-gated too, not just Admin
Management itself. Frontend: `/admin-management` (search/create — an
employee-admin list with pagination, and Create Employee Admin with an
inline permission picker) and `/admin-management/{adminId}` (detail —
role/status, a VIEW/MANAGE/None permission editor with Save/Reset, and
Enable/Disable), both built against the real API above, both under
`Sidebar`'s existing `isModuleVisible()` gating. Covered by 29 frontend
tests (Vitest + React Testing Library, newly added to this app — see
§10's own update below).

4.19 Settings — permission key `SETTINGS` (Super Admin only, never
grantable — BR-126, unchanged)

The original spec named this module but gave no content for it — the
owner's decision #6 supplies the category list. IMPLEMENTED (backend
ADR-0048, 2026-08-28; frontend 2026-08-29, §10 item (13), the last of
the numbered build order — `/settings`). Settings is a navigation
surface over four already-dedicated screens, plus one new generic
table for what has no home yet:

| Category | Where it actually lives | Status |
| :--- | :--- | :--- |
| Fare settings | §4.8 Fare Management (ADR-0042) | Own dedicated screen — Settings links to it |
| Platform fees | §4.8's own new row (ADR-0045) | Own dedicated screen — Settings links to it |
| Referral settings | §4.11's reward config (ADR-0043) | Own dedicated screen — Settings links to it |
| Notification settings | §4.12's Templates (ADR-0044) | Own dedicated screen — Settings links to it |
| Promotion defaults | `GET/PATCH /api/v1/admin/settings/{key}` | IMPLEMENTED — seeded at launch: `welcome_discount_percent`/`welcome_total_uses`, BR-058's own approved values |
| Operational thresholds | same | IMPLEMENTED (mechanism) — none seeded at launch (BR-066's own boundary is still genuinely TBD; nothing else has a documented admin-editability ask) |
| Feature flags | same | IMPLEMENTED (mechanism) — none seeded (nothing in this codebase currently checks a flag) |
| General platform settings | same | IMPLEMENTED (mechanism) — none seeded |

Never exposes API keys, passwords, cloud secrets, DB credentials, or
private keys — those remain exclusively in environment configuration,
outside this table entirely (ADR-0048 §5). See api-contracts.md §46.17.

5. Dashboard-console principle, applied

Per the spec's own stated principle ("this is an operations console,
not just CRUD"), every module above that reaches EXISTS or NEW —
SCOPED status gets, at minimum: a search/find screen, a detail/inspect
view, visible state and (where the domain has one) a history/timeline,
the permitted actions for the current admin's access level, and — for
any module whose actions mutate state — a link to that target's own
slice of the Audit Log (§4.17), not just a global log the admin has to
filter into by hand.

6. Security

- Every new endpoint in this plan sits behind `require_admin` (account
  authentication, unchanged) *and* `require_permission()` (ADR-0040) —
  no admin route is ever permission-exempt except Admin Management
  itself, which is Super-Admin-gated by construction.
- Every mutation is audited (`admin.audit_logs`), matching this
  codebase's existing "reads aren't audited, mutations are" convention
  — extended, not changed, by this plan.
- Session handling reuses the existing phone+OTP flow and JWT access
  tokens (identity module) — no new auth mechanism for the Admin Web.
- CORS: FIXED 2026-08-29. `main.py` now registers `CORSMiddleware`
  (added after `SecurityHeadersMiddleware` so it wraps everything,
  including error responses), reading a new `CORS_ALLOWED_ORIGINS`
  setting (comma-separated, defaults to Next.js's own dev port,
  `http://localhost:3000`) — a real production admin-web origin is
  still undecided, so `infrastructure/kubernetes/backend-configmap.
  yaml` deliberately leaves it unset with a comment rather than
  shipping a guessed value. `allow_credentials=False`: the Admin Web's
  own fetch() calls send a bearer token via the `Authorization` header,
  not cookies, so the credentialed CORS mode was never needed. 4 new
  tests (`tests/test_cors.py`) — allowed-origin header present,
  disallowed-origin header absent, a real preflight OPTIONS request
  answered, and CORS/security headers coexisting on one response. Every
  Admin Web screen this plan describes was unreachable from a real
  browser until this landed, regardless of how many screens existed.

7. Responsive behavior

Desktop-first (this is an internal operations tool, not a
customer-facing surface with meaningful mobile traffic) — but not
desktop-only:
- ≥1280px: full sidebar + content, tables show every column.
- 768–1279px: collapsible sidebar (icon-only, expandable on hover/tap),
  tables drop secondary columns behind a row-expand affordance.
- <768px: sidebar becomes a slide-over drawer; every table becomes a
  stacked card list. Data-entry-heavy screens (Fare Management's
  publish flow, the coupon designer) are usable but not optimized for
  this width — an admin doing that work is assumed to be at a desk.

8. Testing

- Unit: every form's validation logic (fare-rule numeric constraints,
  coupon date-range/limit validation) tested in isolation, no backend
  call.
- Integration: each page's data-fetching against a mocked API client,
  verifying loading/error/empty states are handled (matching this
  codebase's own backend discipline of never leaving an error path
  silently unhandled).
- E2E (a small, high-value set, not exhaustive): login → dashboard
  loads; approve a driver end-to-end; publish a fare-rule version and
  confirm an in-flight ride's already-quoted fare is unaffected (the
  literal "never rewrite historical pricing" requirement, made into a
  test); create → activate a coupon and confirm a second edit attempt
  on an active campaign is rejected.
- Permission enforcement: a dedicated test suite asserting that an
  employee admin with no permission row for a module gets a real `403`
  from the *backend* on every one of that module's mutating endpoints,
  not just a hidden button in the UI — this is the one category of test
  this plan considers non-negotiable, given ADR-0040's own "enforced
  server-side, not just hidden in nav" rule.

9. Deployment

The existing `apps/admin-web` Next.js scaffold already has a CI job
(`admin-web-checks` in `.github/workflows/ci.yml`: lint + build) — this
plan doesn't need a new one, only real pages to lint and build. No
Dockerfile or Kubernetes manifest exists for `admin-web` yet (unlike
the backend, Phase 21/ADR-0035) — deploying it as a real service is a
separate, later task once there's a real app to deploy, following the
same "config/script authorship, no live account needed yet" scope every
other Phase 21 artifact already used.

10. Recommended build order

Not committed, offered as a sequencing suggestion: (1) Admin Management
+ permission model backend is DONE (ADR-0040) — the Admin Web's own
login/create-admin/permissions screens against it are the actual first
frontend build, since every other screen below needs a real admin
session with real permissions to test against; (2) Drivers/Vehicles/
Verification search+detail — backend DONE (2026-08-26, api-contracts.md
§46.4), the biggest immediate gap, reused by GPS Dispute and Support
workflows too; (3) Audit Logs — backend DONE (2026-08-26, §46.3), cheap,
data already existed; (4) Fare Management — backend DONE (2026-08-26,
ADR-0042, §46.7); (5) Offers/Coupons — backend DONE (ADR-0041, §46.2);
(6) Safety/Support admin surfaces — backend DONE (2026-08-26, §46.8/
§46.9); (7) Notifications — history read backend DONE (2026-08-26,
§46.10); broadcast composition turned out to need the same schema
addition Templates already needed (corrected 2026-08-26, §4.12) —
Push/FCM chain remains the long pole; (8) Referral Reward
Configuration — backend DONE (ADR-0043, 2026-08-26, §46.12), the first
of the second decision batch to be implemented, once the owner's
broader "build everything you can without an external credential"
authorization superseded the original design-only-and-stop
instruction; (9) Notification Templates — backend DONE (ADR-0044,
2026-08-26, §46.13), the second; (10) Platform Fee Management —
backend DONE (ADR-0045, 2026-08-26, §46.14), the third; (11)
Advertisements — backend DONE (ADR-0046, 2026-08-26, §46.15), the
fourth; (12) Reports/Analytics — backend DONE (ADR-0047, 2026-08-26,
§46.16), the fifth; (13) Settings — backend DONE (ADR-0048, 2026-08-28,
§46.17), the sixth and last of the second decision batch's own numbered
scope. Items 2-13 are backend-only and implemented — no item from this
decision batch remains backend-designed-but-unimplemented.

(1) itself was built 2026-08-28: the Admin Management screens
(`/admin-management`, `/admin-management/{adminId}`) are the first real
Admin Web frontend in this app, matching this section's own original
sequencing suggestion — (2) through (9) were all built the same day
(see below; (9) was pulled forward to build alongside (7), same
`NOTIFICATIONS` module; (8) then folded in Search Referrals too, same
`REFERRALS` module as the reward-configuration work it was already
building). Items (10) through (13) were then built 2026-08-29 (see
below) — every item this section's own numbered build order named is
now built. Dashboard (built earlier, outside this numbered list — see
§3), Admin Management (§4.18), Customers/Drivers/Vehicles/Verification
(§4.1-§4.4), Audit Logs (§4.17), Fare Management (§4.8, incl. Platform
Fee Management), Offers/Coupons (§4.10), Safety/Support
(§4.13/§4.14), Notifications (§4.12), Referrals (§4.11), Advertisements
(§4.15), Reports/Analytics (§4.16), and Settings (§4.19) have a real
screen at this point in the narrative; the modules that never got a
numbered slot at all — Rides (§4.5), Matching/Offers (§4.6),
Finance/Wallet (§4.7), Penalties/Strikes (§4.9) — were still
backend-only as of item (13) (see further below in this section for
when each was subsequently built: items (14)-(16) plus ADR-0054 closed
all four). Also added in the same pass: this
app's first frontend test
tooling (Vitest + React Testing Library, `npm run test`, wired into the
`admin-web-checks` CI job) — nothing frontend-testable existed to cover
before Admin Management was the first screen with real interaction
(forms, mutations, permission toggling) to test.

(2) was built immediately after, same day: Customers (§4.1, read-only —
search + detail), Drivers (§4.2 — search, detail, Approve/Reject,
Suspend/Reactivate, nested document/verification-case view), Vehicles
(§4.3 — search, detail, Approve/Reject, its own document list — gated
under the VERIFICATION module, not VEHICLES, per api-contracts.md
§46.4, handled as an independently-loading, independently-failing
section rather than assumed to always succeed alongside the vehicle
itself), and Verification (§4.4 — the pending-review queue, defaulting
its status filter to PENDING client-side per that section's own stated
expectation; read-only, since `subject_id` is the underlying document's
own id, not a driver_id/vehicle_id, and no endpoint resolves one back to
the other — deep-linking a queue row to its driver/vehicle would have
had to invent that lookup, so the queue stays informational instead).
7 new routes, all under `Sidebar`'s existing `isModuleVisible()` gating
and `BUILT_HREFS`. 28 more frontend tests (8 new files, on top of the
existing 6 — 57/57 passing total), none of it using the Dashboard's
sample-data fallback pattern, same reasoning as Admin Management's own
build. `npm run lint`, `npx tsc --noEmit`, `npm run test`, and `npm run
build` all clean.

(3) was built next, same day: Audit Logs (§4.17) — `/audit-logs`, a
single read-only search screen (filters: admin ID, action, target
type/id, a from/to date range widened client-side to a full-day
`created_after`/`created_before` boundary, since the backend takes full
ISO datetimes but a plain `<input type="date">` only gives a bare
date). No mutations, so no sample-data-fallback question even arises
here the way it did for (1)/(2). 4 more tests (61/61 total) — lint,
typecheck, tests, and build all clean.

(4) was built next, same day: Fare Management (§4.8, ADR-0042) —
`/fare-management` (list + filters + an inline Create Draft form) and
`/fare-management/{id}` (Submit for Review, Publish with an optional
`datetime-local` `effective_from`). The vehicle-category picker offers
exactly the 5 values `calculate_fare()` keys off
(`BIKE`/`AUTO`/`CAB_ECO`/`CAB_PREMIUM`/`CAB_PREMIUM_PLUS`,
modules/pricing/__init__.py) — a different, CAB-tier-aware vocabulary
from the 3-value `VehicleCategory` Drivers/Vehicles use, easy to
conflate but not the same field. `toneForStatus()` (lib/status-tone.ts,
already shared by Drivers/Vehicles/Verification) gained `PUBLISHED` →
success and `IN_REVIEW` → warning rather than a fourth, one-off status
map. Platform Fee Management (§10 item (10), same DRAFT/IN_REVIEW/
PUBLISHED shape but a separate table/permission, `FINANCE`) is
deliberately not included here — still backend-only. 9 more tests
(70/70 total) — lint, typecheck, tests, and build all clean.

(5) was built next, same day: Offers/Coupons (§4.10, ADR-0041) —
`/offers-coupons` (list, status filter, an inline Create Campaign
form) and `/offers-coupons/{id}` (Edit while `status=DRAFT`, then
Activate/Pause/End). One `CampaignForm` (13 fields) is shared by Create
(POST) and Edit (PATCH) rather than two near-duplicate forms — the
backend, not this component, is what actually enforces PATCH-only-in-
DRAFT (INVALID_STATE_TRANSITION otherwise); the form itself doesn't
re-derive that rule, it's just never shown for a non-DRAFT campaign.
`eligible_customer_ids` (only meaningful when `eligible_scope=
SELECTED`) is a plain textarea, one ID per line or comma-separated,
parsed client-side into the UUID list the API already expected — not
the CSV-bulk-upload endpoint (§4.10's own table, `NEW — SCOPED`, still
unbuilt at either layer). `datetime-local` inputs for `starts_at`/
`ends_at` convert to/from the backend's UTC ISO timestamps in local
time, not a raw UTC string shown in a control that looks local. 14 more
tests (84/84 total) — lint, typecheck, tests, and build all clean.

(6) was built next, same day: Safety/SOS (§4.13, ADR-0022) —
`/safety`, `/safety/{id}` (Acknowledge/Escalate/Resolve, each shown
only for the one status that actually allows it, matching
state-machines.md §45's linear OPEN→ACKNOWLEDGED→IN_PROGRESS→RESOLVED
lifecycle) — and Support/Disputes (§4.14) — `/support`, `/support/{id}`
(Resolve, plus the full message conversation, not just case fields).
GPS Dispute (§4.14's own 4th row) was deliberately left out — its own
text already treats it as a separate, pre-existing surface (§77,
BR-124/125), not new work this item's own scope covers, same "flag
what's excluded, don't fold it in silently" treatment already given to
Platform Fee Management (item (4)) and CSV bulk targeting (item (5)).
`lib/status-tone.ts` gained `RESOLVED`→success, `IN_PROGRESS`/
`WAITING_FOR_USER`→warning, and `OPEN`/`ASSIGNED`/`ACKNOWLEDGED`→info —
the first extension to reuse an existing tone bucket (`info`, until now
only `PENDING`) rather than adding a new one. 15 more tests (99/99
total) — lint, typecheck, tests, and build all clean.

(7) and (9) were built together next, same day, out of numeric order —
both live under §4.12's single `NOTIFICATIONS` permission key and plan
section, so building Notification History (item (7)) without also
building Templates (item (9), backend done the same day as (7) per
§10's own text) would have split one Admin Web module's frontend across
two separate sessions of work for no real reason; (8) Referral Reward
Configuration remains next, not skipped, just deferred one slot.
`/notifications` (delivery history — filters: channel, status; no
detail screen, deliveries have no further action) links to
`/notifications/templates` (list, filters, an inline Create Template
form) and `/notifications/templates/{id}` (Publish, DRAFT only). No
Edit endpoint exists for templates (ADR-0044 Decision 4: an edit is
always a new Create, versioned) — the frontend doesn't invent one.
Compose/Send Broadcast, Audience Selection, and device-token
registration remain exactly what §4.12's own table already says: NEEDS
SCOPING, not touched here. 11 more tests (110/110 total) — lint,
typecheck, tests, and build all clean.

(8) was built next, same day: Referral Reward Configuration (§4.11,
ADR-0043) — and, since §4.11 also names Search Referrals (backend done
the same day as the config work) as its own row under the identical
`REFERRALS` permission key, that was folded in too rather than left as
a separate future slot, same reasoning already applied to (7)/(9).
`/referrals` (search + status filter; each row's own reward(s) shown
inline via `Pill`, not a drill-down — the API already composes them)
links to `/referrals/rewards`, a single page hosting both independent
config streams side by side: Driver Referral Bonus (one global policy)
and Customer Referral Rewards (one per `reward_type` —
REFERRAL_REFERRED/REFERRAL_REFERRING, a config-level vocabulary that
looks similar to but is distinct from `ReferralReward`'s own
DRIVER_REFERRAL_BONUS/CUSTOMER_REFERRAL_PROMOTION `reward_type`, a
different table entirely). Each stream gets its own inline create form,
status filter, and detail route
(`/referrals/rewards/driver-bonus/{id}`, `.../customer/{id}`) for
Submit-for-Review/Publish — the same DRAFT→IN_REVIEW→PUBLISHED shape
Fare Management (item (4)) and Notification Templates (item (9))
already established, reused rather than redesigned a third time.
`lib/status-tone.ts` gained `ACTIVATED`→success (`ReferralStatus`,
distinct from the existing `ACTIVE` case — a different literal string,
not a typo) and `SENT`/`FAILED` (`DeliveryStatus`, picked up as a side
effect of auditing every status value now flowing through this shared
map). 15 more tests (125/125 total) — lint, typecheck, tests, and build
all clean.

(10) was built 2026-08-29: Platform Fee Management (§4.8's own row,
ADR-0045) — `/fare-management/platform-fee` (list + filters + an
inline Create Draft form) and `/fare-management/platform-fee/{id}`
(Submit for Review, Publish with an optional `datetime-local`
`effective_from`), reached via a "Platform Fee Management →" link on
`/fare-management` rather than its own sidebar entry — `nav.ts` maps
one `AdminModule` to one href, and Platform Fee has no module of its
own (ADR-0045 Decision 3 deliberately reuses `FINANCE`, not
`FARE_MANAGEMENT`, so a Fare-Management-only admin sees the link but
gets the same FORBIDDEN handling as any other screen if they lack
`FINANCE`). Component-for-component the same DRAFT→IN_REVIEW→PUBLISHED
shape as Fare Management (item (4)), Notification Templates (item (9)),
and Referral Reward Configuration (item (8)) — reused, not redesigned a
fourth time — but the 3-key `VehicleCategory` vocabulary
(BIKE/AUTO/CAB) `platform_fee_rules` actually keys off, not Fare
Management's 5-key CAB-tier set (ADR-0045 Decision 1's own point:
BR-011's platform fee applies uniformly across CAB's tiers). Also
folded into this session, as read-only corrections rather than new
work: Dashboard's Online Drivers widget reclassified IMPLEMENTED (the
ADR-0011 Redis go_offline-cleanup bug was found already fixed in the
current code, closing §4.6's technical blocker on the identical figure
even though §4.6 itself still has no screen), and device-token
registration (ADR-0052) reclassified IMPLEMENTED, distinguished from
the still-open production Firebase credential (external dependency)
and from Compose/Send Broadcast + Audience Selection (a separate,
still-NEEDS-SCOPING feature ADR-0052 doesn't touch) — see §3, §4.6,
and §4.12 above. 9 more tests (134/134 total) — lint, typecheck, tests,
and build all clean.

(11) was built 2026-08-29: Advertisements (§4.15, ADR-0046) — the
largest single module built this session, three independent resources
sharing one `ADVERTISEMENTS` permission. `/advertisements` (campaign
list + status filter + inline Create Campaign form) and
`/advertisements/{id}` (Pause/Resume/End per `CampaignStatus`'s new
ACTIVE⇄PAUSED→ENDED lifecycle, an inline "Assign a driver" form —
disabled with an explanatory message once the campaign isn't ACTIVE,
matching `CampaignNotActiveError` server-side — and that campaign's own
assignments listed inline); `/advertisements/assignments` (the global
installation/proof review queue, filterable by campaign ID/driver
ID/status — freeform ID inputs, no picker component, same precedent
Offers/Coupons' own `eligible_customer_ids` textarea already
established, since no such component exists anywhere in this app to
reuse) and `/advertisements/assignments/{id}` (Approve/Reject proof,
shown only while `PROOF_SUBMITTED`; "Calculate payout," shown only
once `VERIFIED`, renders the resulting payout inline); `/advertisements
/payouts` (payout/settlement monitoring, status filter, an inline
Settle button per PENDING row). `lib/status-tone.ts` gained
`VERIFIED`/`PAID`→success and `PAUSED`/`PROOF_SUBMITTED`→warning;
`ENDED` was deliberately left unmapped (falls to the existing
`neutral` default), the same treatment already given to Safety's own
`CLOSED` — terminal isn't the same as bad. New types are `Ad`-prefixed
(`AdCampaign`, `AdCampaignStatus`, `AdAssignment`, `AdPayout`) to avoid
colliding with Offers/Coupons' own unrelated `Campaign`/`CampaignStatus`
— same English word, two different domains, easy to conflate. 21 more
tests (155/155 total) — lint, typecheck, tests, and build all clean.

(12) was built 2026-08-29: Reports/Analytics (§4.16, ADR-0047) —
`/reports`, one page hosting all nine fixed-shape reports behind a
single report-type picker and a shared `from`/`to` date range, rather
than nine near-identical routes for nine reports that share nothing but
their permission and a date filter. The `<input type="date">` range
widens to a full-day boundary before it's sent, the same convention
Audit Logs already established, and an empty range is left empty
rather than guessed at client-side — the backend's own 30-day default
(ADR-0047 §2) decides that, and the response's own `from`/`to` fields
(the range actually used) are what the page displays, not the raw
input values. Each report's fetched shape is mapped to a small,
uniform `{stats, breakdowns}` view — scalar numbers/rates/currency as
stat cards, `Record<string, number>` fields (e.g. `rides_by_status`) as
breakdown lists — one shared renderer for nine different response
shapes rather than nine bespoke layouts. VIEW-only permission; no
mutations exist in this module, so no sample-data-fallback question
and no audit-log entries either, matching every other pure-read
admin endpoint already in this codebase. 4 more tests (159/159 total)
— lint, typecheck, tests, and build all clean.

(13) was built 2026-08-29, the last item of the numbered build order:
Settings (§4.19, ADR-0048) — `/settings`, a navigation surface, not a
second place to edit fare/platform-fee/referral/notification data
that already has its own dedicated screen (ADR-0048 Decision 1): four
link cards at the top of the page point straight at `/fare-management`,
`/fare-management/platform-fee`, `/referrals/rewards`, and
`/notifications/templates`. Below that, the actual `admin.settings`
table — the four categories with no home elsewhere (promotion
defaults, operational thresholds, feature flags, general) — as a
category-filterable list with inline editing: `value` is a bare JSON
scalar/object with no per-key schema (ADR-0048 §4), so the edit control
is a textarea pre-filled with `JSON.stringify(value, null, 2)`,
`JSON.parse`d back on Save with a real validation-error banner (not a
silent failure) if the typed text isn't valid JSON. A plain overwrite,
not a DRAFT/IN_REVIEW/PUBLISHED lifecycle — ADR-0048 Decision 3's own
point: nothing reads `admin.settings` live at transaction time the way
Fare/Platform Fee do, so the extra workflow machinery buys nothing
here. `SETTINGS` is Super-Admin-only and never grantable (BR-126,
unchanged) — the only module in this app with no partial-access case
to design for. 5 more tests (164/164 total) — lint, typecheck, tests,
and build all clean.

This closes out every item §10 itself ever numbered (1 through 13).
What remained unbuilt at the frontend — Rides (§4.5), Matching/Offers
(§4.6), Finance/Wallet (§4.7), and Penalties/Strikes (§4.9) — was never
assigned a slot in this section's own sequencing to begin with (a real
gap in the plan's own numbering, not a deferral), and Matching/Offers'
own backend blocker (the ADR-0011 Redis go_offline gap) is now
resolved per §3/§4.6 above. The build order continues past 13, in the
order the owner named when asking to continue past the original list:

(14) was built 2026-08-29: Rides (§4.5) — `/rides` (search by
driver/customer ID and status, freeform ID inputs, same no-picker-
component precedent Advertisements' assignment queue already set) and
`/rides/{id}` (a read-only lifecycle timeline — Requested → Accepted →
Driver arrived → Started → Completed/Cancelled → Closed, each step
showing its own timestamp or an em dash if not yet reached — plus
pickup/destination coordinates and the fare breakdown when one
exists). No action exists anywhere on this screen; no admin-side ride
intervention (force-cancel, reassign) was ever asked for, so nothing
was invented to fill that gap. `lib/status-tone.ts` gained
`ACCEPTED`/`COMPLETED`→success, `CANCELLED`→danger,
`STARTED`→warning, and `SEARCHING`/`ARRIVED`→info; `CLOSED` (Rides)
joins `ENDED` (Ad campaigns) as a second deliberately-unmapped
terminal-but-not-bad status. 6 more tests (170/170 total) — lint,
typecheck, tests, and build all clean.

(15) was built 2026-08-29: Finance / Wallet (§4.7) — `/finance`, a
driver-ID lookup form (no search-all-wallets endpoint exists by
design; a wallet is looked up by a known `driver_id`, not browsed), and
`/finance/{driverId}` (balance + outstanding settlement, then the
transaction history table with a type filter over all 10
`TransactionType` values and pagination). `useRouter().push()` is this
app's first use of programmatic navigation — every other screen so far
navigates via `<Link>`, but a lookup-then-navigate flow with no list to
click a row in has nothing to attach a `<Link>` to until the ID is
known, so a router push on submit is the natural fit rather than
forcing a `<Link>` pattern where it doesn't apply. `CREDIT`/`DEBIT`
direction gets an inline `Pill` (`success`/`neutral`) rather than a
`toneForStatus()` entry — it's a fixed 2-value field, not a status enum
this shared map already tracks many of. 6 more tests (176/176 total)
— lint, typecheck, tests, and build all clean.

(16) was built 2026-08-29: Penalties / Strikes (§4.9) — `/penalties`
(search by user ID and status, plus the only documented resolve
action, Waive: clicking it opens an inline reason row directly below
the target penalty rather than a separate detail page — the same
"nothing here needs a whole second screen" reasoning Advertisements'
inline Settle button already established for a one-field mutation).
Driver Strike History was checked against the current backend, not
assumed from the plan doc's own text — `GET /api/v1/admin/drivers/
{id}/strikes` still does not exist (verified: no matching route in
`modules/admin/router.py`), so it stays exactly what §4.9's own table
already says, NEW — SCOPED, and isn't folded into this screen.
`lib/status-tone.ts` gained `SETTLED`/`WAIVED`→success and
`OUTSTANDING`→info — `EXPIRED` already existed from an earlier module.
5 more tests (181/181 total) — lint, typecheck, tests, and build all
clean.

Only Matching/Offers (§4.6) remained, and its documented endpoint did
not exist yet — inventing it without a decision would have been
exactly the kind of new API contract this codebase's own §0.3 stops
for. A scoping report was produced (this same date) inspecting the
current matching backend, Redis GEO state, offer lifecycle, Reports,
and Dashboard, and presenting three tiers (A: surface only what
already exists, zero new backend; B: A plus a per-category online
count; C: real search over individual offers, optionally with a live
driver-location map). The owner chose Tier C, explicitly excluding the
location-map half — recorded as ADR-0054.

(17) was built 2026-08-29, closing the last item in the 20-module
catalog: Matching/Offers (§4.6, ADR-0054) — `/matching` (online-driver
count, total and by real `matching_category_key()` value — BIKE/AUTO/
CAB:ECO/CAB:PREMIUM/CAB:PREMIUM_PLUS, not a coarser grouping — plus a
search form over individual offers: status/ride ID/driver ID/date
range, same freeform-ID-input precedent already established) and
`/matching/{offerId}` (documented/safe fields only — offer_id, ride_id,
driver_id, vehicle_id, status, expires_at, responded_at, created_at;
no coordinates, no Redis-derived location or availability data). Two
new backend endpoints (`GET .../matching/online-drivers`,
`GET .../matching/offers[/{id}]`), a new `OfferRepository.search()`
(mirroring `RideService.search_rides()`'s own shape exactly) and
`MatchingService.get_offer()` (mirroring `RideService.get_ride()`'s
admin-only-no-ownership-check split), and a new `geo.
count_online_drivers_by_category()` (the same ZCARD loop `count_
online_drivers()` already sums, just not collapsed). No driver-location
map, no live coordinates anywhere in the response — the owner's
explicit exclusion, left for a separate future decision. No mutation
exists in this module or was proposed — the matching algorithm itself
(driver-facing, `modules/matching/router.py`) is untouched. 20 new
backend tests (6 unit against a fake repository, 14 real-Postgres/
real-Redis integration tests dispatching an actual offer end-to-end)
— full backend suite 1197 passed, 5 skipped (pre-existing Kafka-only
skips), ruff and mypy clean. Frontend: `/matching` (online-driver stat
cards + search form) and `/matching/{offerId}` (documented-fields-only
summary card), 7 more tests (188/188 total) — lint, typecheck, tests,
and build all clean. See
`docs/14-decisions/ADR-0054-matching-offers-admin-visibility.md`,
`docs/05-api/api-contracts.md` §46.20, and this document's §4.6 and
§10, all updated.

Every module in the original 20-item catalog now has a real Admin Web
screen. CORS was fixed the same day (§6) — the last thing standing
between those screens and actually working in a real browser.

(18) was built 2026-08-29: Driver Strike History (§4.9, api-contracts.md
§46.18) — the first of the three remaining NEW — SCOPED items,
picked up after the 20-module catalog itself was complete. New
`StrikeRepository.list_for_driver()` (newest-first, paginated — a
strike is immutable by construction, no status/date filter needed the
way Search Penalties/Search Offers have one) and a new
`GET /api/v1/admin/drivers/{id}/strikes` endpoint, reusing the DRIVERS
permission (this is driver data, not a new module, api-contracts.md
§46.18's own reasoning) — same existence check Admin Wallet View
already does for an unknown driver_id (404, not an empty page).
Frontend: `/drivers/{driverId}/strikes`, a plain paginated table
(reason, ride, recorded-at), reached via a new "View history →" link
next to the strikes count already shown on `/drivers/{id}` — no new
sidebar entry, same sub-route-reached-via-a-link pattern already used
for Platform Fee Management and Referral Reward Configuration. No
action exists on this screen; `driver.drivers.strikes` stays the
at-a-glance summary counter, this is the underlying detail view. 8 new
backend tests (3 unit against a fake repository, 5 real-Postgres
integration) — full backend suite 1209 passed, 5 skipped
(pre-existing, unrelated), ruff and mypy clean. Frontend: 5 more tests
(192/192 total) — lint, typecheck, tests, and build all clean.

(19) was built 2026-08-29: CSV Bulk Customer Targeting (§4.10, ADR-0041
§9) — the second of the three remaining NEW — SCOPED items. New
`CampaignRepository.add_eligible_customers()` (additive, idempotent —
re-adding an already-eligible customer_id is a no-op, returns only the
newly-added subset) alongside the existing `set_eligible_customers()`
(replace semantics, used by Create/Edit) — the two coexist because
ADR-0041 §9 deliberately gives bulk upload the opposite semantics: a
re-uploaded refreshed list must never silently drop individually-added
customers. New `PromotionService.bulk_add_eligible_customers()` enforces
the same `can_edit()`/DRAFT gate Edit Campaign already has, plus a new
`eligible_scope='SELECTED'`-only check (`InvalidCampaignInputError`,
VALIDATION_FAILED). New `POST /api/v1/admin/campaigns/{id}/eligible-
customers/bulk`, multipart/form-data, resolving each CSV row's phone to
a customer_id via the same two-step check (identity.accounts phone
lookup, then a customer.customers existence check) Customer Detail's
own composition already performs — an unmatched row is reported back
with its row number/phone/reason, never silently dropped or treated as
a whole-request failure. Pulled in `python-multipart` as a new runtime
dependency (FastAPI's own multipart parsing needs it; the endpoint
would 500 on a real upload without it despite importing cleanly).
Frontend: a file input + Upload button on `/offers-coupons/{id}`,
shown only while DRAFT and `eligible_scope='SELECTED'`, reporting
added/already_eligible/unmatched back inline via a new `apiUpload()`
client helper (this app's first multipart request — deliberately sets
no Content-Type header, letting the browser attach its own boundary).
11 new backend tests (4 unit against a fake repository, 7
real-Postgres integration) — full backend suite 1220 passed, 5 skipped
(pre-existing, unrelated), ruff and mypy clean. Frontend: 4 more tests
(196/196 total) — lint, typecheck, tests, and build all clean.

(20) was built 2026-08-29: GPS Dispute frontend (§4.14). The backend
required only a single new endpoint, `GET /api/v1/admin/gps-disputes/
{dispute_id}`, composing the pre-existing, pre-tested
`RideService.get_gps_dispute()` — no new domain or service code, per
this codebase's established "service exists, no HTTP route" pattern
(Driver Suspension, Safety Acknowledge/Escalate/Resolve). 3 new
backend tests — full backend suite 1223 passed, 5 skipped
(pre-existing, unrelated), ruff and mypy clean. Frontend: new
`/support/gps-disputes` list (status filter, pagination) and
`/support/gps-disputes/{disputeId}` detail (evidence table, conditional
Approve/Reject with a required decision reason) routes, linked from a
new "GPS Disputes →" nav item on the Support page; 8 new tests — full
suite 50 files/204 tests passed, tsc/lint/build all clean. See
`docs/05-api/api-contracts.md` §77 and this file's own §4.14 row,
both updated.

This closed out every item in the Admin Web implementation plan's
original scope that didn't require a fresh decision: all 20 sidebar
modules plus every NEW — SCOPED sub-item (Driver Strike History, CSV
Bulk Customer Targeting, GPS Dispute frontend), plus the cross-cutting
CORS fix that made these screens reachable from a real browser. One
genuinely NEEDS-SCOPING item remained — §4.12's Compose/Send Broadcast
+ Audience Selection, which needed its own owner decision (a real
schema addition Templates alone didn't supply) rather than an
invented design.

(21) was built 2026-08-29, closing that last item: Compose/Send
Broadcast + Audience Selection (§4.12, ADR-0055 Tier C). A scoping
report presented three tiers (A: trigger an existing published
Template, no free text; B: A plus true one-off free-text composition;
C: B plus scheduling); the owner chose Tier C. New `notification.
broadcasts` table — a broadcast's own free-text subject/body publishes
a one-off, broadcast-only `notification.templates` row under the hood
(`event_key=NULL`, exactly ADR-0044's own schema comment's anticipated
case), so every recipient's actual send still goes through `Notification
Service.send()` unchanged. Three new endpoints (`POST/GET .../
notifications/broadcasts`, `GET .../{id}`), a new shared `modules.
notification.broadcast_dispatch` module (`resolve_audience()` +
`dispatch_broadcast()`, used identically by the immediate-send path and
a new Celery Beat task polling every 5 minutes for due scheduled
broadcasts), and new audience-resolution methods (`CustomerService.
list_all_customer_ids()`, `DriverService.list_all_driver_ids()`, `geo.
list_online_driver_ids()`). No change to `NotificationService.send()`'s
single-recipient signature — the fan-out lives one layer above it, as
scoped. 21 new backend tests (10 unit against a fake repository, 8 unit
against fakes for the dispatch module, 11 real-Postgres/real-Redis
integration across `test_admin_api.py`, 2 real-Postgres integration for
the scheduled-dispatch task in `test_notification_tasks.py`) — full
backend suite 1254 passed, 5 skipped (pre-existing, unrelated), ruff
and mypy clean. Frontend: `/notifications/broadcasts` (compose form —
channel/audience/schedule/message — plus history list) and `/
notifications/broadcasts/{id}` (read-only detail), linked from a new
"Broadcasts →" item on the Notifications page; 8 new tests — full
suite 52 files/212 tests passed, tsc/lint/build all clean. See
`docs/04-database/database-design.md` §32.5, `docs/05-api/api-
contracts.md` §46.21, `docs/14-decisions/ADR-0055-notification-
broadcast-composition.md`, and this file's own §4.12 row, all updated.

This closes out every item in the Admin Web implementation plan's
original scope, including the one item that needed its own fresh
decision rather than an invented design: all 20 sidebar modules, every
NEW — SCOPED sub-item, the cross-cutting CORS fix, and the one
NEEDS-SCOPING item (Compose/Send Broadcast + Audience Selection,
ADR-0055). No item from this plan's original scope remains
outstanding.
