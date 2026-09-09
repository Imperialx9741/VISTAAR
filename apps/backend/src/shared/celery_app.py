"""Background Worker Foundation — Celery application object (ADR-0039).

Redis (already provisioned — see core/redis.py, core/config.py's
REDIS_URL) serves as both broker and result backend; no new
infrastructure dependency. Unlike shared/outbox_publisher.py's and
modules/notification/consumer.py's in-process asyncio tasks (ADR-0017,
ADR-0038), Celery's execution model is a genuinely separate OS process —
this module defines the app object; nothing in main.py imports or starts
it. Run it with:

    celery -A shared.celery_app worker --beat --loglevel=info

(a single combined worker+beat process — ADR-0039 Decision 2: Beat must
never run more than one instance, so this is deliberately not split
into two separately-scaled processes yet).

Task modules register their own periodic tasks against this app object
(see modules/notification/tasks.py) — imported here so `celery -A
shared.celery_app` discovers them without needing a separate
`include=[...]` list to keep in sync by hand.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from core.config import settings

celery_app = Celery(
    "vistaar",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.timezone = "UTC"

# Imported for its side effect (registering @celery_app.task-decorated
# functions) — must come after `celery_app` is defined above, since
# modules/notification/tasks.py imports it back.
import modules.notification.tasks  # noqa: E402,F401
import modules.ride.tasks  # noqa: E402,F401

celery_app.conf.beat_schedule = {
    "check-expiring-promotions": {
        "task": "notification.check_expiring_promotions",
        # An arbitrary, low-traffic hour — not a documented business
        # value, just when to run (ADR-0039 Decision 3).
        "schedule": crontab(hour=2, minute=0),
    },
    "check-expiring-documents": {
        "task": "notification.check_expiring_documents",
        "schedule": crontab(hour=2, minute=15),
    },
    "send-scheduled-broadcasts": {
        "task": "notification.send_scheduled_broadcasts",
        # Unlike the two once-a-day scans above, a scheduled broadcast
        # (ADR-0055) names a specific scheduled_at an admin actually
        # chose — polling every 5 minutes keeps the gap between that
        # moment and the real send small without needing a genuine
        # push-based scheduler, the same "correct first" tradeoff this
        # codebase already accepted for Search Rides'/Search Offers'
        # own lack of a dedicated index (ADR-0054's own reasoning).
        "schedule": crontab(minute="*/5"),
    },
    "promote-due-scheduled-rides": {
        "task": "ride.promote_due_scheduled_rides",
        # ADR-0057 — same 5-minute polling cadence and "correct first,
        # not fastest possible" reasoning as send-scheduled-broadcasts
        # above, against a 30-minute lock-in window
        # (SCHEDULED_RIDE_LOCK_IN_WINDOW).
        "schedule": crontab(minute="*/5"),
    },
    "retry-failed-notifications": {
        "task": "notification.retry_failed_notifications",
        # ADR-0075 — same 5-minute cadence as the two tasks above; each
        # FAILED delivery is retried exactly once no matter how often
        # this runs (retry_count=0 is the exclusivity condition, not a
        # time window), so a shorter interval only shortens how long a
        # transient outage's retry is delayed, never causes a double
        # retry.
        "schedule": crontab(minute="*/5"),
    },
}
