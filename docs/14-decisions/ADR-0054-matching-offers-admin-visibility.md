ADR-0054 — Matching / Offers Admin Visibility (Tier C)

Status: Accepted and implemented (2026-08-29) — owner decision, choosing
Tier C of the three scoping options presented in this ADR's own
preceding scoping report (2026-08-29). Resolves Admin Web §4.6's
"NEW — NEEDS SCOPING" flag, the last of the 20-module catalog to get
one.

Date recorded: 2026-08-29.
Deciders: Project owner (explicit written decision, 2026-08-29,
"Choose Tier C... Do NOT add a live driver-location map yet... Keep the
map/location capability as a separate future decision").

1. Context

Every other Admin Web module either had a real backend already or got
one from the owner's 2026-08-26 decision batch. Matching/Offers never
did — the plan's own §4.6 table named one candidate screen ("Live
online-driver map/count") and marked it NEW — NEEDS SCOPING, "real-time
operational visibility, not a screen with persisted history like every
other module here."

The preceding scoping report (this same date) inspected the current
matching backend, Redis GEO state, offer lifecycle, Reports/Analytics,
and Dashboard, and found: no search/list capability exists for
individual `matching.ride_offers` rows (only per-driver/per-ride
PENDING-only lookups used by the driver-facing flow, and two aggregate
methods Reports already consumes); no per-category online-driver
breakdown exists (only a single summed total, Dashboard's own); and no
enumeration of *who* is online with their location exists at all. That
report offered three tiers (A: zero new backend, just surface what
Dashboard/Reports already have; B: A plus a per-category count; C: real
search over individual offers, plus optionally a live driver-location
map). The owner chose C, explicitly excluding the location-map half of
it.

2. Decision 1 — Online driver count, total and by category

```
GET /api/v1/admin/matching/online-drivers
{"by_category": {"BIKE": n, "AUTO": n, "CAB:ECO": n, "CAB:PREMIUM": n,
                  "CAB:PREMIUM_PLUS": n}, "total": n}
```

Reuses the same accurate `geo.count_online_drivers()` count Dashboard's
summary already sums (real since the ADR-0011 go_offline-cleanup fix),
via a new `geo.count_online_drivers_by_category()` that returns the
same per-key ZCARD without collapsing it into one sum. Keyed by the
real `matching_category_key()` values (BIKE/AUTO/CAB:ECO/CAB:PREMIUM/
CAB:PREMIUM_PLUS) — not a coarser 3-value grouping — because CAB's
tiers are genuinely separate Redis keys (ADR-0020 Decision 1) and
collapsing them would hide real information the index already has.

3. Decision 2 — Search and detail over individual offers

```
GET /api/v1/admin/matching/offers?status=&ride_id=&driver_id=&from=&to=&page=&page_size=
GET /api/v1/admin/matching/offers/{offer_id}
```

A new `OfferRepository.search()` method (allow-listed filters, same
"no client-supplied field name" discipline `modules/ride/repositories.
py`'s own `search()` already documents), backing a new
`MatchingService.search_offers()` pass-through — identical shape to
`RideService.search_rides()`. `from`/`to` filter on `created_at` with
**no default range** (unlike Reports' own 30-day default) — this is a
search screen, not a report; an omitted bound means "no filter on that
side," matching Search Rides'/Search Penalties' own treatment of
optional filters. Ordered newest-first, same convention every other
admin search endpoint uses. No new index was added — `ride.rides` (the
closest precedent, Search Rides) has none for its own status/date
filters either; this is the same accepted tradeoff, not a new one.

`GET .../offers/{offer_id}` is a new `MatchingService.get_offer()`
(unrestricted, no driver-ownership check) mirroring `RideService.
get_ride()`'s already-established "no ownership restriction,
admin-only" split from the driver-facing lookup.

Response shape (both endpoints), documented/safe fields only —
`database-design.md` §10.1's actual columns, nothing derived from
Redis:

```
{"offer_id", "ride_id", "driver_id", "vehicle_id", "status",
 "expires_at", "responded_at", "created_at"}
```

4. Decision 3 — No driver-location map, no live coordinates (explicit
   exclusion, not an oversight)

The owner's decision explicitly carved this out: "Do NOT add a live
driver-location map yet. Do NOT expose real-time driver coordinates to
Admin Web." Nothing in this ADR's two endpoints returns a latitude,
longitude, or any other Redis-derived per-driver field beyond the
count. `shared/geo.py` gained no enumeration method (e.g. a `ZRANGE`
over `geo:drivers:{category}`) — only the per-category `ZCARD` breakdown
above. A live map, if ever wanted, is its own separate future ADR,
starting fresh from that undecided question rather than inheriting
anything from this one.

5. Decision 4 — Permission

`AdminModule.MATCHING` (already in the 20-module catalog, BR-126) —
VIEW only. This is MATCHING's first real consumer anywhere in the
codebase. No MANAGE-gated action exists or is proposed: the matching
algorithm itself (`modules/matching/router.py`, driver-facing) is
untouched by this ADR, and no admin mutation control was requested or
built — an admin can see offers and counts, never act on them.

6. What this does NOT resolve

- A live driver-location map or any real-time coordinate exposure to
  Admin Web — Decision 3, deliberately deferred to a separate future
  decision, not scoped or designed here at all.
- Driver current availability / current-ride-state in the Redis
  online-driver hash — `technical-architecture.md` §14 documents these
  as conceptually part of driver state, but `shared/geo.py`'s actual
  write only ever sets latitude/longitude/vehicle_id/vehicle_category/
  updated_at (ADR-0011's own deliberate restraint, re-verified against
  current code by the preceding scoping report). Unrelated to and not
  needed by anything this ADR builds.
- Publishing the documented `matching.offer_created`/`offer_rejected`/
  `offer_expired` events (`event-contracts.md` §11) — still blocked on
  Kafka producer infrastructure not existing (ADR-0011 Decision 2's own
  scope), unrelated to admin visibility.
- Any change to the matching algorithm, dispatch logic, or offer
  lifecycle — this ADR is read-only visibility into what already
  happens, nothing here changes when or to whom an offer is dispatched.

7. Consequences — documents updated alongside this ADR

- `api-contracts.md` §46.20: the two new endpoint shapes, implemented.
- `docs/15-admin-web/admin-web-implementation-plan.md` §4.6 and §10:
  Matching/Offers moves from NEW — NEEDS SCOPING to IMPLEMENTED
  (backend + frontend), closing the last item in the 20-module catalog.
- `docs/VISTAAR_IMPLEMENTATION_ROADMAP.md`: dated narrative entry for
  this build.
