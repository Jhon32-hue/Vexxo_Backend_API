"""
Publicacion confiable de eventos del contexto de identidad.

Descripcion general:
- encapsula la salida de eventos de `identity` al bus de dominio
- usa outbox persistente para no perder eventos de `users`, `devices`,
  `sessions`, `consents` o `permissions`

Analisis detallado:
- `identity` ya coordina registro, sesiones, dispositivos, consentimientos y
  permisos; por criticidad, no es suficiente publicar solo con
  `transaction.on_commit`
- este servicio delega en `identity.eventing`, dejando la misma garantia base
  que ya existe en `finance.accounts`
"""

from __future__ import annotations

import hashlib
import json

from common.domain_events import EventContext, EventPriority
from identity.eventing.services import publish_identity_after_commit


def _stable_identity_aggregate_id(*, event_type: str, payload: dict, metadata: dict | None = None, correlation_id: str | None = None) -> str:
    metadata = metadata or {}
    payload = payload or {}
    if payload.get("user_id"):
        return str(payload["user_id"])
    if payload.get("entity_id"):
        return str(payload["entity_id"])
    if correlation_id:
        return str(correlation_id)
    if payload.get("provider") and payload.get("state"):
        return hashlib.sha256(str(payload["state"]).encode("utf-8")).hexdigest()[:32]
    if payload.get("provider") and payload.get("provider_user_id"):
        return f"{payload['provider']}:{payload['provider_user_id']}"
    raw = json.dumps(
        {
            "event_type": event_type,
            "payload": payload,
            "metadata_source": metadata.get("source", ""),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _resolve_identity_aggregate_type(payload: dict) -> str:
    payload = payload or {}
    if payload.get("user_id"):
        return "identity_user"
    entity_type = str(payload.get("entity_type") or "").strip()
    if entity_type:
        return f"identity_{entity_type}"
    if payload.get("provider") or payload.get("state"):
        return "identity_flow"
    return EventContext.IDENTITY.value


def publish_user_event_after_commit(
    *,
    event_type: str,
    payload: dict,
    metadata: dict | None = None,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    aggregate_type = _resolve_identity_aggregate_type(payload or {})
    aggregate_id = _stable_identity_aggregate_id(
        event_type=event_type,
        payload=payload or {},
        metadata=metadata,
        correlation_id=correlation_id,
    )
    publish_identity_after_commit(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        metadata=metadata or {},
        priority=priority,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
