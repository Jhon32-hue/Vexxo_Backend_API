from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.db import transaction


def local_outbox_autopublish_enabled() -> bool:
    return bool(getattr(settings, "DOMAIN_EVENTS_LOCAL_AUTOPUBLISH_ENABLED", False))


def schedule_local_outbox_autopublish(
    event,
    *,
    reload_event: Callable[[object], object | None],
    publish_event: Callable[[object], None],
) -> bool:
    if not event or getattr(event, "published_at", None) or not local_outbox_autopublish_enabled():
        return False
    if getattr(event, "_local_publish_scheduled", False):
        return False

    event._local_publish_scheduled = True

    def _publish_local_event() -> None:
        fresh = reload_event(event.pk)
        if fresh is None or getattr(fresh, "published_at", None):
            return
        publish_event(fresh)

    transaction.on_commit(_publish_local_event)
    return True
