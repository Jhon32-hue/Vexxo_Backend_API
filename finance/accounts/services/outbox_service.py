"""
Helpers de eventos de dominio especificos de accounts.

Descripcion general:
- encapsula la publicacion consistente de eventos `accounts.*`
- prepara el modulo para una arquitectura event-driven con outbox + consumidores

Analisis detallado:
- `event_service.py` resuelve el mecanismo generico; este modulo expresa los
  eventos concretos del bounded context de cuentas
- asi evitamos duplicar payloads, idempotency keys y metadata en views, use
  cases o signals
- el mismo contrato sirve hoy para el bus local y manana para Pub/Sub,
  workers en Cloud Run o pipelines desacoplados

Que se puede hacer despues:
- agregar dispatchers hacia Pub/Sub o Cloud Tasks sin tocar el dominio
- enriquecer metadata con tenant, request_id o tracing distribuido
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from common.domain_events import EventContext

from finance.accounts.domain.events import (
    AccountDomainEventTypes,
    build_account_balance_payload,
    build_account_membership_payload,
    build_account_sync_payload,
)

from finance.accounts.services.event_service import enqueue_domain_event, publish_after_commit
from finance.accounts.services.realtime_services import ping_account_changed


def _stable_event_key(event_type: str, aggregate_id: str | int, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{event_type}:{aggregate_id}:{digest}"


def _account_event_metadata(metadata: dict | None = None) -> dict:
    return {
        "context": EventContext.ACCOUNTS.value,
        "source": "accounts.outbox_service",
        **(metadata or {}),
    }


def _touch_account_last_domain_event(account) -> None:
    account.__class__.objects.filter(pk=account.pk).update(last_domain_event_at=timezone.now())


def enqueue_account_event(
    *,
    account,
    event_type: str,
    payload: dict,
    metadata: dict | None = None,
):
    _touch_account_last_domain_event(account)
    return enqueue_domain_event(
        aggregate_type="account",
        aggregate_id=str(account.pk),
        event_type=event_type,
        idempotency_key=_stable_event_key(event_type, account.pk, payload),
        payload=payload,
        metadata=_account_event_metadata(metadata),
    )


def publish_account_lifecycle_event(
    *,
    account,
    event_type: str,
    payload: dict,
    metadata: dict | None = None,
):
    event = enqueue_account_event(
        account=account,
        event_type=event_type,
        payload=payload,
        metadata=metadata,
    )
    publish_after_commit(event)
    return event


def publish_account_event(
    *,
    account,
    event_type: str,
    payload: dict,
    metadata: dict | None = None,
):
    event = enqueue_account_event(
        account=account,
        event_type=event_type,
        payload=payload,
        metadata=metadata,
    )
    publish_after_commit(event)
    return event


def enqueue_account_balance_updated_event(
    *,
    account,
    old_balance: Decimal,
    new_balance: Decimal,
    reason: str,
    transaction_id: str | int | None = None,
    metadata: dict | None = None,
):
    payload = build_account_balance_payload(
        account=account,
        old_balance=old_balance,
        new_balance=new_balance,
        reason=reason,
        transaction_id=transaction_id,
    )
    return enqueue_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_BALANCE_UPDATED,
        payload=payload,
        metadata=metadata,
    )


def publish_account_balance_updated(
    *,
    account,
    old_balance: Decimal,
    new_balance: Decimal,
    reason: str,
    transaction_id: str | int | None = None,
    metadata: dict | None = None,
):
    if Decimal(str(new_balance)) == Decimal(str(old_balance)):
        return None

    event = enqueue_account_balance_updated_event(
        account=account,
        old_balance=old_balance,
        new_balance=new_balance,
        reason=reason,
        transaction_id=transaction_id,
        metadata=metadata,
    )

    transaction.on_commit(
        lambda: ping_account_changed(
            owner_id=account.owner_id,
            account_id=account.pk,
            event="account.balance.changed",
            extra={"reason": reason},
        )
    )
    publish_after_commit(event)
    return event


def publish_account_sync_event(
    *,
    account,
    event_type: str,
    change: str,
    extra: dict | None = None,
    metadata: dict | None = None,
):
    event = enqueue_account_event(
        account=account,
        event_type=event_type,
        payload=build_account_sync_payload(account=account, change=change, extra=extra),
        metadata=metadata,
    )
    publish_after_commit(event)
    return event


def publish_account_membership_event(
    *,
    membership,
    event_type: str,
    change: str,
    extra: dict | None = None,
    metadata: dict | None = None,
):
    _touch_account_last_domain_event(membership.account)
    event = enqueue_domain_event(
        aggregate_type="account",
        aggregate_id=str(membership.account_id),
        event_type=event_type,
        idempotency_key=_stable_event_key(
            event_type,
            membership.account_id,
            build_account_membership_payload(membership=membership, change=change, extra=extra),
        ),
        payload=build_account_membership_payload(membership=membership, change=change, extra=extra),
        metadata=_account_event_metadata(metadata),
    )
    publish_after_commit(event)
    return event
