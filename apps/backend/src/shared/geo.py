"""Redis GEO helpers backing the driver geo index.

domain-design.md §10.2 assigns "driver geo index" ownership to the
Matching Domain (modules/matching/), not modules/driver/ — this module
is a thin, matching-agnostic wrapper around the two Redis structures
technical-architecture.md §14 documents:

    geo:drivers:{CATEGORY}     GEO set, member = driver_id, used for
                                GEOSEARCH (nearest-first candidate
                                lookup).
    driver:online:{driver_id}  HASH: latitude, longitude, vehicle_id,
                                vehicle_category, updated_at.

Only these four hash fields are written. technical-architecture.md §14
also lists "Availability" and "Current ride state" as fields a driver's
online record could carry, but Task 3.2 does not implement Accept Offer
(ADR-0011 Decision 3) — nothing in this task can ever make a driver's
Redis-tracked availability differ from Postgres's authoritative
driver.drivers.operational_status, so populating those two fields now
would be untested, unused state. modules/matching/service.py re-verifies
operational_status against Postgres at match time regardless (Redis is
only ever used here as a spatial index, never as the source of truth for
eligibility) — see that module's docstring.

Removing a driver from the index on go_offline was NOT wired up by
Task 3.2 — see ADR-0011 for why that was a flagged, not silent, scope
trim at the time: matching's eligibility re-check against Postgres
means a stale Redis entry can never produce an incorrect offer, only a
wasted eligibility check for an offline driver. It IS wired up now
(2026-08-28, modules/driver/router.py's go_offline endpoint composes
remove_driver_location() below) — the Admin Web Dashboard's "Online
drivers" widget (count_online_drivers() below) is what finally needed
this index to stop growing forever, not a matching-correctness concern.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis

_GEO_KEY_PREFIX = "geo:drivers:"
_ONLINE_HASH_PREFIX = "driver:online:"


def _geo_key(category: str) -> str:
    return f"{_GEO_KEY_PREFIX}{category}"


def _online_hash_key(driver_id: uuid.UUID) -> str:
    return f"{_ONLINE_HASH_PREFIX}{driver_id}"


async def upsert_driver_location(
    redis_client: Redis,
    *,
    driver_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    category: str,
    latitude: float,
    longitude: float,
) -> None:
    await redis_client.geoadd(_geo_key(category), (longitude, latitude, str(driver_id)))
    # redis-py's hset() stub is shared between the sync and async client
    # base classes and types as Union[Awaitable[int], int] as a result —
    # unsound for `await` in mypy's eyes even though the async client
    # always actually returns an awaitable at runtime. Surfaced by
    # ADR-0039's celery[redis] dependency pulling in redis-py 6.x
    # (previously unpinned, older stubs didn't hit this).
    await redis_client.hset(  # type: ignore[misc]
        _online_hash_key(driver_id),
        mapping={
            "latitude": latitude,
            "longitude": longitude,
            "vehicle_id": str(vehicle_id),
            "vehicle_category": category,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


async def remove_driver_location(
    redis_client: Redis, *, driver_id: uuid.UUID, category: str
) -> None:
    """Called from modules/driver/router.py's go_offline endpoint
    (wired up 2026-08-28 — see this module's own docstring for the
    history: written well before anything called it, exactly so a
    future task wiring go_offline to clean up the index wouldn't have
    to reinvent it)."""
    await redis_client.zrem(_geo_key(category), str(driver_id))
    await redis_client.delete(_online_hash_key(driver_id))


async def count_online_drivers(redis_client: Redis, *, category_keys: list[str]) -> int:
    """Admin Web Dashboard's "Online drivers" widget (admin-web-
    implementation-plan.md §3) — real now that go_offline() actually
    calls remove_driver_location() (see modules/driver/router.py's
    go_offline endpoint), so a driver's geo:drivers:{category} entry no
    longer outlives their session. Sums ZCARD across every category key
    the caller passes (this module stays matching-agnostic per its own
    docstring — the caller builds the real category list via
    modules.vehicle's VehicleCategory/CabTier + matching_category_key()).
    A GEO set is backed by a sorted set, so ZCARD is the right count,
    cheaper than GEOSEARCH. A driver appears under at most one category
    key at a time (BR-122: at most one ACTIVE vehicle), so summing
    across keys never double-counts."""
    total = 0
    for category in category_keys:
        total += await redis_client.zcard(_geo_key(category))
    return total


async def count_online_drivers_by_category(
    redis_client: Redis, *, category_keys: list[str]
) -> dict[str, int]:
    """Admin Web Matching/Offers screen (ADR-0054) — the same ZCARD
    count count_online_drivers() sums, but keyed per category instead
    of collapsed into one total, so an admin can see the BIKE/AUTO/
    CAB:ECO/CAB:PREMIUM/CAB:PREMIUM_PLUS breakdown (the real
    matching_category_key() values, not a coarser 3-value grouping —
    CAB's tiers are genuinely separate Redis keys, ADR-0020 Decision 1).
    Deliberately does not return anything about *which* drivers are in
    each set or their locations (ADR-0054 explicitly excludes a live
    driver-location map) — only the count."""
    return {
        category: await redis_client.zcard(_geo_key(category))
        for category in category_keys
    }


async def list_online_driver_ids(
    redis_client: Redis, *, category_keys: list[str]
) -> list[uuid.UUID]:
    """Admin Web Notification Broadcast's "Online drivers" audience
    (ADR-0055) — unlike count_online_drivers()/count_online_drivers_by_
    category(), returns the actual driver_id members (ZRANGE, not
    ZCARD) so a broadcast can resolve who to actually send to. A driver
    appears in at most one category key at a time (BR-122), so no
    driver_id is ever duplicated across the category keys summed here."""
    ids: list[uuid.UUID] = []
    for category in category_keys:
        members = await redis_client.zrange(_geo_key(category), 0, -1)
        ids.extend(uuid.UUID(str(member)) for member in members)
    return ids


async def nearest_driver_ids(
    redis_client: Redis,
    *,
    category: str,
    latitude: float,
    longitude: float,
    radius_km: float,
    limit: int,
) -> list[uuid.UUID]:
    """Nearest-first driver_ids within radius_km of (latitude,
    longitude) currently present in geo:drivers:{category}. Presence
    here only means "was ONLINE with this vehicle category as of their
    last location write" — not a guarantee of current eligibility; see
    this module's docstring."""
    raw_ids = await redis_client.geosearch(
        _geo_key(category),
        longitude=longitude,
        latitude=latitude,
        radius=radius_km,
        unit="km",
        sort="ASC",
        count=limit,
    )
    return [uuid.UUID(str(raw_id)) for raw_id in raw_ids]
