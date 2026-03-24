"""
Servicios de senalizacion realtime para accounts.

Descripcion general:
- emite avisos livianos post-commit para UI, polling o futuros gateways
- persiste senales minimas para no depender solo de logs ni del bus de dominio

Analisis detallado:
- `finance.accounts` ya publica eventos de dominio para integraciones, alertas y
  analytics, pero la UX tambien necesita una capa operativa mas cercana a la UI
- `RealtimeSignal` funciona como inbox tecnico liviano para polling, SSE o
  futuros gateways WebSocket
- esta capa no reemplaza al outbox ni a `notifications.deliveries`; los
  complementa con senales breves y de bajo costo para superficies interactivas
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from realtime.consumers.models import RealtimeSignal

logger = logging.getLogger(__name__)


def create_realtime_signal(
    *,
    owner_id: int,
    channel: str,
    event: str,
    aggregate_type: str = "",
    aggregate_id: str = "",
    payload: dict[str, Any] | None = None,
) -> RealtimeSignal:
    normalized_payload = dict(payload or {})
    signal = RealtimeSignal.objects.create(
        owner_id=owner_id,
        channel=(channel or "system")[:64],
        event=(event or "system.changed")[:128],
        aggregate_type=(aggregate_type or "")[:64],
        aggregate_id=(aggregate_id or "")[:64],
        payload=normalized_payload,
    )
    transaction.on_commit(lambda: signal.mark_published())
    logger.info(
        "[realtime] signal=%s owner_id=%s aggregate=%s:%s",
        signal.event,
        owner_id,
        signal.aggregate_type,
        signal.aggregate_id,
    )
    return signal


def publish_account_realtime_signal(
    *,
    owner_id: int,
    account_id: int,
    event: str,
    extra: dict[str, Any] | None = None,
) -> RealtimeSignal:
    payload = {
        "event": event,
        "owner_id": owner_id,
        "account_id": account_id,
        "extra": extra or {},
    }
    return create_realtime_signal(
        owner_id=owner_id,
        channel="accounts",
        event=event,
        aggregate_type="account",
        aggregate_id=str(account_id),
        payload=payload,
    )


def ping_account_changed(
    *,
    owner_id: int,
    account_id: int,
    event: str = "account.changed",
    extra: dict[str, Any] | None = None,
) -> None:
    publish_account_realtime_signal(
        owner_id=owner_id,
        account_id=account_id,
        event=event,
        extra=extra,
    )
