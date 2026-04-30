"""
Servicios de persistencia de notificaciones.

Descripcion general:
- centraliza la creacion y deduplicacion de notificaciones persistentes
- desacopla listeners de dominio del modelo concreto de inbox
"""

from __future__ import annotations

from notifications.deliveries.models import NotificationChannel, NotificationDelivery, NotificationStatus


def create_notification_delivery(
    *,
    owner,
    title: str,
    message: str,
    event_type: str = "",
    source: str = "",
    payload: dict | None = None,
    channel: str = NotificationChannel.IN_APP,
    dedupe_key: str = "",
    mark_delivered_immediately: bool = True,
) -> NotificationDelivery:
    payload = payload or {}
    normalized_dedupe = (dedupe_key or "").strip()

    if normalized_dedupe:
        obj, _created = NotificationDelivery.objects.get_or_create(
            dedupe_key=normalized_dedupe,
            defaults={
                "owner": owner,
                "channel": channel,
                "event_type": event_type,
                "source": source,
                "title": title[:180],
                "message": message,
                "payload": payload,
            },
        )
        if mark_delivered_immediately and obj.status == NotificationStatus.PENDING:
            obj.mark_delivered()
        return obj

    obj = NotificationDelivery.objects.create(
        owner=owner,
        channel=channel,
        event_type=event_type,
        source=source,
        title=title[:180],
        message=message,
        payload=payload,
        dedupe_key=None,
    )
    if mark_delivered_immediately:
        obj.mark_delivered()
    return obj
