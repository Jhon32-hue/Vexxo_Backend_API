"""
Proyeccion operativa de uso de producto por usuario.

Este modulo mueve el calculo de usage fuera del request path:
- el BFF lee una proyeccion compacta y no consulta OLTP en cada request
- los productores del dominio refrescan la proyeccion desde eventos o hooks
- deja preparado el camino para reemplazar el rebuild por proyectores
  incrementales, Cloud Tasks o Dataflow sin cambiar la API de producto
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

ZERO = Decimal("0.00")
PAYMENT_COUNTABLE_STATUSES = {"created", "dispatched", "processing", "requires_action", "succeeded", "settled"}


def month_bounds(reference=None):
    anchor = reference or timezone.now()
    start = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def day_bounds(reference=None):
    anchor = reference or timezone.now()
    start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timezone.timedelta(days=1)
    return start, end


def _scheduled_payments_active_count_for_user(user) -> int:
    from payments.scheduled_payments.models import PaymentTemplate

    return PaymentTemplate.objects.filter(owner=user, is_active=True).count()


def compute_user_usage_snapshot_from_oltp(user, *, reference=None) -> dict:
    from alerts.alerts.models.alerts import Alert
    from alerts.rules.models import Rule
    from finance.accounts.models import Account, AccountMembership, AccountStatus
    from payments.payment_intents.models import PaymentIntent

    start, end = month_bounds(reference=reference)
    day_start, day_end = day_bounds(reference=reference)

    active_statuses = [AccountStatus.ACTIVE, AccountStatus.FROZEN]
    accounts_qs = Account.objects.filter(owner=user, status__in=active_statuses)
    connected_qs = accounts_qs.exclude(provider="").exclude(external_id="")
    manual_qs = accounts_qs.filter(provider="", external_id="")

    membership_qs = AccountMembership.objects.filter(account__owner=user).exclude(user_id=user.id)
    pending_or_active_memberships = membership_qs.filter(
        Q(is_active=True)
        | Q(
            is_active=False,
            revoked_at__isnull=True,
            invitation_sent_at__isnull=False,
            accepted_at__isnull=True,
        )
    )

    ai_qs = Alert.objects.filter(owner=user, created_at__gte=start, created_at__lt=end).filter(
        Q(ai_summary__gt="") | Q(type="ai_insight")
    )

    payment_qs = PaymentIntent.objects.filter(
        owner=user,
        created_at__gte=start,
        created_at__lt=end,
        status__in=PAYMENT_COUNTABLE_STATUSES,
    )
    payment_qs_day = PaymentIntent.objects.filter(
        owner=user,
        created_at__gte=day_start,
        created_at__lt=day_end,
        status__in=PAYMENT_COUNTABLE_STATUSES,
    )
    from payments.payment_intents.models import PayoutInstruction

    payout_qs = PayoutInstruction.objects.filter(
        batch__owner=user,
        created_at__gte=start,
        created_at__lt=end,
        status__in={
            PayoutInstruction.Status.CREATED,
            PayoutInstruction.Status.DISPATCHED,
            PayoutInstruction.Status.SUCCEEDED,
        },
    )
    payout_qs_day = PayoutInstruction.objects.filter(
        batch__owner=user,
        created_at__gte=day_start,
        created_at__lt=day_end,
        status__in={
            PayoutInstruction.Status.CREATED,
            PayoutInstruction.Status.DISPATCHED,
            PayoutInstruction.Status.SUCCEEDED,
        },
    )
    payment_volume = payment_qs.aggregate(total=Sum("amount"))["total"] or ZERO
    payment_volume_day = payment_qs_day.aggregate(total=Sum("amount"))["total"] or ZERO
    payout_volume = payout_qs.aggregate(total=Sum("amount"))["total"] or ZERO
    payout_volume_day = payout_qs_day.aggregate(total=Sum("amount"))["total"] or ZERO

    return {
        "usage_version": 1,
        "current_period_start": start,
        "current_period_end": end,
        "current_day_start": day_start,
        "current_day_end": day_end,
        "manual_accounts_count": manual_qs.count(),
        "connected_accounts_count": connected_qs.count(),
        "active_accounts_count": accounts_qs.count(),
        "rules_count": Rule.objects.filter(owner=user, active=True).count(),
        "ai_used_month": ai_qs.count(),
        "payments_count_month": payment_qs.count(),
        "payments_volume_month": payment_volume,
        "payments_count_day": payment_qs_day.count(),
        "payments_volume_day": payment_volume_day,
        "payouts_count_month": payout_qs.count(),
        "payouts_volume_month": payout_volume,
        "payouts_count_day": payout_qs_day.count(),
        "payouts_volume_day": payout_volume_day,
        "ocr_used_month": 0,
        "scheduled_payments_active_count": _scheduled_payments_active_count_for_user(user),
        "shared_memberships_count": pending_or_active_memberships.count(),
    }


def rebuild_user_usage_projection(
    user,
    *,
    reference=None,
    source: str = "",
    event_type: str = "",
    correlation_id: str = "",
):
    from identity.eventing.models import UserProductUsageProjection

    usage = compute_user_usage_snapshot_from_oltp(user, reference=reference)
    projection, _created = UserProductUsageProjection.objects.update_or_create(
        owner=user,
        defaults={
            **usage,
            "last_source": str(source or "")[:128],
            "last_event_type": str(event_type or "")[:128],
            "last_correlation_id": str(correlation_id or "")[:64],
        },
    )
    return projection


def _ensure_projection(user):
    from identity.eventing.models import UserProductUsageProjection

    projection = UserProductUsageProjection.objects.filter(owner=user).first()
    if projection is not None:
        return projection
    return rebuild_user_usage_projection(
        user,
        source="identity.users.product_usage_projection.ensure_projection",
    )


def _apply_projection_metadata(projection, *, source: str = "", event_type: str = "", correlation_id: str = ""):
    projection.last_source = str(source or "")[:128]
    projection.last_event_type = str(event_type or "")[:128]
    projection.last_correlation_id = str(correlation_id or "")[:64]


def _clamp_non_negative(value) -> int:
    return max(0, int(value or 0))


def _stringify(value) -> str:
    return str(value or "").strip()


def _event_fingerprint(*, owner_id, event_id: str, event_type: str, payload: dict | None = None) -> str:
    raw = json.dumps(
        {
            "owner_id": str(owner_id or ""),
            "event_id": str(event_id or ""),
            "event_type": str(event_type or ""),
            "payload": payload or {},
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mark_projection_event_processed(owner_id, *, event, source: str = "") -> bool:
    from identity.eventing.models import UserProductUsageProjectionEvent

    metadata = dict(getattr(event, "metadata", None) or {})
    event_id = (
        _stringify(metadata.get("projection_event_key"))
        or _stringify(metadata.get("outbox_event_id"))
        or _stringify(getattr(event, "id", ""))
    )
    if not event_id or not owner_id:
        return True

    try:
        UserProductUsageProjectionEvent.objects.create(
            owner_id=owner_id,
            event_id=event_id[:64],
            event_type=_stringify(getattr(event, "type", ""))[:128],
            correlation_id=_stringify(getattr(event, "correlation_id", ""))[:64],
            fingerprint=_event_fingerprint(
                owner_id=owner_id,
                event_id=event_id,
                event_type=getattr(event, "type", ""),
                payload=getattr(event, "payload", None),
            )[:160],
            source=_stringify(source)[:128],
        )
        return True
    except IntegrityError:
        return False


def _apply_event_once(owner_id, *, event, source: str = "", apply=None):
    if not owner_id or event is None or apply is None:
        return None
    if not _mark_projection_event_processed(owner_id, event=event, source=source):
        return None
    return apply()


def mutate_user_usage_projection(
    user,
    *,
    source: str = "",
    event_type: str = "",
    correlation_id: str = "",
    mutator=None,
):
    from identity.eventing.models import UserProductUsageProjection

    if user is None or mutator is None:
        return None

    _ensure_projection(user)
    with transaction.atomic():
        projection = UserProductUsageProjection.objects.select_for_update().filter(owner=user).first()
        if projection is None:
            projection = rebuild_user_usage_projection(
                user,
                source=source,
                event_type=event_type,
                correlation_id=correlation_id,
            )
            projection = UserProductUsageProjection.objects.select_for_update().get(pk=projection.pk)
        mutator(projection)
        _apply_projection_metadata(
            projection,
            source=source,
            event_type=event_type,
            correlation_id=correlation_id,
        )
        projection.save()
    return projection


def refresh_user_usage_projection_by_owner_id(
    owner_id,
    *,
    source: str = "",
    event_type: str = "",
    correlation_id: str = "",
):
    from django.contrib.auth import get_user_model

    if not owner_id:
        return None
    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return None
    return rebuild_user_usage_projection(
        user,
        source=source,
        event_type=event_type,
        correlation_id=correlation_id,
    )


def refresh_user_usage_projection_from_event(owner_id, *, event, source: str = ""):
    def apply():
        return refresh_user_usage_projection_by_owner_id(
            owner_id,
            source=source,
            event_type=getattr(event, "type", ""),
            correlation_id=getattr(event, "correlation_id", "") or "",
        )

    return _apply_event_once(owner_id, event=event, source=source, apply=apply)


def increment_rules_usage(owner_id, *, delta: int, source: str = "", event_type: str = "", correlation_id: str = ""):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return None

    def mutator(projection):
        projection.rules_count = _clamp_non_negative(projection.rules_count + int(delta or 0))

    return mutate_user_usage_projection(
        user,
        source=source,
        event_type=event_type,
        correlation_id=correlation_id,
        mutator=mutator,
    )


def _bucket_from_account_fields(*, status, provider, external_id) -> dict:
    status_value = _stringify(status).lower()
    provider_value = _stringify(provider)
    external_value = _stringify(external_id)
    active = status_value in {"active", "frozen"}
    connected = bool(provider_value and external_value)
    manual = active and not connected
    return {
        "active": bool(active),
        "connected": bool(active and connected),
        "manual": bool(manual),
    }


def _bucket_from_account_payload(payload: dict | None) -> dict:
    payload = payload or {}
    return _bucket_from_account_fields(
        status=payload.get("status"),
        provider=payload.get("provider"),
        external_id=payload.get("external_id"),
    )


def _counted_bucket_from_provider_fields(*, provider, external_id) -> dict:
    connected = bool(_stringify(provider) and _stringify(external_id))
    return {
        "active": True,
        "connected": bool(connected),
        "manual": not connected,
    }


def _account_bucket_transition_from_event(event) -> tuple[dict, dict]:
    event_type = _stringify(getattr(event, "type", ""))
    payload = dict(getattr(event, "payload", None) or {})
    before = dict(payload.get("before") or {})
    after = dict(payload.get("after") or {})

    if event_type == "accounts.created.v1":
        return {"active": False, "connected": False, "manual": False}, _bucket_from_account_payload(payload)

    if event_type in {"accounts.closed.v1", "accounts.archived.v1"}:
        before_bucket = _counted_bucket_from_provider_fields(
            provider=payload.get("provider"),
            external_id=payload.get("external_id"),
        )
        return before_bucket, {"active": False, "connected": False, "manual": False}

    if event_type == "accounts.unarchived.v1":
        return {"active": False, "connected": False, "manual": False}, _bucket_from_account_payload(payload)

    if event_type == "accounts.external.linked.v1":
        current = _bucket_from_account_payload(payload)
        if not current["active"]:
            return current, current
        before_bucket = dict(current)
        before_bucket["connected"] = False
        before_bucket["manual"] = True
        return before_bucket, current

    if event_type == "accounts.external.unlinked.v1":
        current = _bucket_from_account_payload(payload)
        if not current["active"]:
            return current, current
        before_bucket = dict(current)
        before_bucket["connected"] = True
        before_bucket["manual"] = False
        return before_bucket, current

    if before and after:
        return _bucket_from_account_payload(before), _bucket_from_account_payload(after)

    current = _bucket_from_account_payload(payload)
    return current, current


def apply_account_usage_event_delta(owner_id, *, event, source: str = ""):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None or event is None:
        return None

    def apply():
        before_bucket, after_bucket = _account_bucket_transition_from_event(event)
        manual_delta = int(after_bucket["manual"]) - int(before_bucket["manual"])
        connected_delta = int(after_bucket["connected"]) - int(before_bucket["connected"])
        active_delta = int(after_bucket["active"]) - int(before_bucket["active"])

        if not any([manual_delta, connected_delta, active_delta]):
            return mutate_user_usage_projection(
                user,
                source=source,
                event_type=getattr(event, "type", ""),
                correlation_id=getattr(event, "correlation_id", "") or "",
                mutator=lambda projection: None,
            )

        def mutator(projection):
            projection.manual_accounts_count = _clamp_non_negative(projection.manual_accounts_count + manual_delta)
            projection.connected_accounts_count = _clamp_non_negative(projection.connected_accounts_count + connected_delta)
            projection.active_accounts_count = _clamp_non_negative(projection.active_accounts_count + active_delta)

        return mutate_user_usage_projection(
            user,
            source=source,
            event_type=getattr(event, "type", ""),
            correlation_id=getattr(event, "correlation_id", "") or "",
            mutator=mutator,
        )

    return _apply_event_once(owner_id, event=event, source=source, apply=apply)


def _membership_counts_as_shared(payload: dict | None) -> bool:
    payload = payload or {}
    if _stringify(payload.get("user_id")) == _stringify(payload.get("owner_id")):
        return False
    if bool(payload.get("is_active")):
        return True
    invitation_status = _stringify(payload.get("invitation_status")).lower()
    accepted_at = payload.get("accepted_at")
    revoked_at = payload.get("revoked_at")
    return bool(invitation_status in {"pending", "opened"} and not accepted_at and not revoked_at)


def _membership_transition_from_event(event) -> tuple[bool, bool]:
    event_type = _stringify(getattr(event, "type", ""))
    payload = dict(getattr(event, "payload", None) or {})
    metadata = dict(payload.get("projection_transition") or {})

    if "before_counted" in metadata or "after_counted" in metadata:
        return bool(metadata.get("before_counted")), bool(metadata.get("after_counted"))

    if event_type == "accounts.membership.created.v1":
        return False, _membership_counts_as_shared(payload)

    if event_type == "accounts.membership.invited.v1":
        return _membership_counts_as_shared(payload), _membership_counts_as_shared(payload)

    if event_type == "accounts.membership.accepted.v1":
        return True, True

    if event_type == "accounts.membership.revoked.v1":
        return True, False

    current = _membership_counts_as_shared(payload)
    return current, current


def apply_shared_membership_event_delta(owner_id, *, event, source: str = ""):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None or event is None:
        return None

    def apply():
        before_counted, after_counted = _membership_transition_from_event(event)
        delta = int(after_counted) - int(before_counted)

        if delta == 0:
            return mutate_user_usage_projection(
                user,
                source=source,
                event_type=getattr(event, "type", ""),
                correlation_id=getattr(event, "correlation_id", "") or "",
                mutator=lambda projection: None,
            )

        def mutator(projection):
            projection.shared_memberships_count = _clamp_non_negative(projection.shared_memberships_count + delta)

        return mutate_user_usage_projection(
            user,
            source=source,
            event_type=getattr(event, "type", ""),
            correlation_id=getattr(event, "correlation_id", "") or "",
            mutator=mutator,
        )

    return _apply_event_once(owner_id, event=event, source=source, apply=apply)


def sync_ai_usage_slice(owner_id, *, reference=None, source: str = "", event_type: str = "", correlation_id: str = ""):
    from alerts.alerts.models.alerts import Alert
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return None
    start, end = month_bounds(reference=reference)
    day_start, day_end = day_bounds(reference=reference)
    count = Alert.objects.filter(owner=user, created_at__gte=start, created_at__lt=end).filter(
        Q(ai_summary__gt="") | Q(type="ai_insight")
    ).count()

    def mutator(projection):
        projection.current_period_start = start
        projection.current_period_end = end
        projection.ai_used_month = _clamp_non_negative(count)

    return mutate_user_usage_projection(
        user,
        source=source,
        event_type=event_type,
        correlation_id=correlation_id,
        mutator=mutator,
    )


def apply_ai_usage_event_delta(owner_id, *, event, source: str = "", reference=None):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None or event is None:
        return None

    event_reference = reference or getattr(event, "created_at", None) or timezone.now()
    start, end = month_bounds(reference=event_reference)

    def apply():
        projection = _ensure_projection(user)
        if projection.current_period_start != start or projection.current_period_end != end:
            return sync_ai_usage_slice(
                owner_id,
                reference=event_reference,
                source=source,
                event_type=getattr(event, "type", ""),
                correlation_id=getattr(event, "correlation_id", "") or "",
            )

        def mutator(record):
            record.current_period_start = start
            record.current_period_end = end
            record.ai_used_month = _clamp_non_negative(record.ai_used_month + 1)

        return mutate_user_usage_projection(
            user,
            source=source,
            event_type=getattr(event, "type", ""),
            correlation_id=getattr(event, "correlation_id", "") or "",
            mutator=mutator,
        )

    return _apply_event_once(owner_id, event=event, source=source, apply=apply)


def sync_ai_usage_from_event(owner_id, *, event, source: str = "", reference=None):
    def apply():
        return sync_ai_usage_slice(
            owner_id,
            reference=reference,
            source=source,
            event_type=getattr(event, "type", ""),
            correlation_id=getattr(event, "correlation_id", "") or "",
        )

    return _apply_event_once(owner_id, event=event, source=source, apply=apply)


def apply_payment_usage_event_delta(owner_id, *, event, source: str = ""):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None or event is None:
        return None

    payload = dict(getattr(event, "payload", None) or {})
    transition = dict(payload.get("usage_transition") or {})
    amount = Decimal(str(transition.get("amount") or payload.get("amount") or "0"))
    event_reference = getattr(event, "created_at", None) or timezone.now()
    start, end = month_bounds(reference=event_reference)
    day_start, day_end = day_bounds(reference=event_reference)

    def apply():
        projection = _ensure_projection(user)
        if (
            projection.current_period_start != start
            or projection.current_period_end != end
            or projection.current_day_start != day_start
            or projection.current_day_end != day_end
        ):
            return sync_payments_usage_slice(
                owner_id,
                reference=event_reference,
                source=source,
                event_type=getattr(event, "type", ""),
                correlation_id=getattr(event, "correlation_id", "") or "",
            )

        before_counted = bool(transition.get("before_counted"))
        after_counted = bool(transition.get("after_counted"))
        count_delta = int(after_counted) - int(before_counted)
        volume_delta = amount if after_counted and not before_counted else ZERO
        if before_counted and not after_counted:
            volume_delta = -amount

        def mutator(record):
            record.current_period_start = start
            record.current_period_end = end
            record.current_day_start = day_start
            record.current_day_end = day_end
            record.payments_count_month = _clamp_non_negative(record.payments_count_month + count_delta)
            record.payments_volume_month = (Decimal(str(record.payments_volume_month or "0")) + volume_delta).quantize(Decimal("0.01"))
            if record.payments_volume_month < ZERO:
                record.payments_volume_month = ZERO
            record.payments_count_day = _clamp_non_negative(record.payments_count_day + count_delta)
            record.payments_volume_day = (Decimal(str(record.payments_volume_day or "0")) + volume_delta).quantize(Decimal("0.01"))
            if record.payments_volume_day < ZERO:
                record.payments_volume_day = ZERO

        return mutate_user_usage_projection(
            user,
            source=source,
            event_type=getattr(event, "type", ""),
            correlation_id=getattr(event, "correlation_id", "") or "",
            mutator=mutator,
        )

    return _apply_event_once(owner_id, event=event, source=source, apply=apply)


def apply_payout_usage_event_delta(owner_id, *, event, source: str = ""):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None or event is None:
        return None

    payload = dict(getattr(event, "payload", None) or {})
    transition = dict(payload.get("usage_transition") or {})
    amount = Decimal(str(transition.get("amount") or payload.get("amount") or "0"))
    event_reference = getattr(event, "created_at", None) or timezone.now()
    start, end = month_bounds(reference=event_reference)
    day_start, day_end = day_bounds(reference=event_reference)

    def apply():
        projection = _ensure_projection(user)
        if (
            projection.current_period_start != start
            or projection.current_period_end != end
            or projection.current_day_start != day_start
            or projection.current_day_end != day_end
        ):
            return sync_payouts_usage_slice(
                owner_id,
                reference=event_reference,
                source=source,
                event_type=getattr(event, "type", ""),
                correlation_id=getattr(event, "correlation_id", "") or "",
            )

        before_counted = bool(transition.get("before_counted"))
        after_counted = bool(transition.get("after_counted"))
        count_delta = int(after_counted) - int(before_counted)
        volume_delta = amount if after_counted and not before_counted else ZERO
        if before_counted and not after_counted:
            volume_delta = -amount

        def mutator(record):
            record.current_period_start = start
            record.current_period_end = end
            record.current_day_start = day_start
            record.current_day_end = day_end
            record.payouts_count_month = _clamp_non_negative(record.payouts_count_month + count_delta)
            record.payouts_volume_month = (Decimal(str(record.payouts_volume_month or "0")) + volume_delta).quantize(Decimal("0.01"))
            if record.payouts_volume_month < ZERO:
                record.payouts_volume_month = ZERO
            record.payouts_count_day = _clamp_non_negative(record.payouts_count_day + count_delta)
            record.payouts_volume_day = (Decimal(str(record.payouts_volume_day or "0")) + volume_delta).quantize(Decimal("0.01"))
            if record.payouts_volume_day < ZERO:
                record.payouts_volume_day = ZERO

        return mutate_user_usage_projection(
            user,
            source=source,
            event_type=getattr(event, "type", ""),
            correlation_id=getattr(event, "correlation_id", "") or "",
            mutator=mutator,
        )

    return _apply_event_once(owner_id, event=event, source=source, apply=apply)


def sync_accounts_usage_slice(owner_id, *, source: str = "", event_type: str = "", correlation_id: str = ""):
    from django.contrib.auth import get_user_model
    from finance.accounts.models import Account, AccountStatus

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return None

    active_statuses = [AccountStatus.ACTIVE, AccountStatus.FROZEN]
    accounts_qs = Account.objects.filter(owner=user, status__in=active_statuses)
    connected_count = accounts_qs.exclude(provider="").exclude(external_id="").count()
    manual_count = accounts_qs.filter(provider="", external_id="").count()
    active_count = accounts_qs.count()

    def mutator(projection):
        projection.manual_accounts_count = _clamp_non_negative(manual_count)
        projection.connected_accounts_count = _clamp_non_negative(connected_count)
        projection.active_accounts_count = _clamp_non_negative(active_count)

    return mutate_user_usage_projection(
        user,
        source=source,
        event_type=event_type,
        correlation_id=correlation_id,
        mutator=mutator,
    )


def sync_shared_memberships_slice(owner_id, *, source: str = "", event_type: str = "", correlation_id: str = ""):
    from django.contrib.auth import get_user_model
    from finance.accounts.models import AccountMembership

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return None

    membership_qs = AccountMembership.objects.filter(account__owner=user).exclude(user_id=user.id)
    count = membership_qs.filter(
        Q(is_active=True)
        | Q(
            is_active=False,
            revoked_at__isnull=True,
            invitation_sent_at__isnull=False,
            accepted_at__isnull=True,
        )
    ).count()

    def mutator(projection):
        projection.shared_memberships_count = _clamp_non_negative(count)

    return mutate_user_usage_projection(
        user,
        source=source,
        event_type=event_type,
        correlation_id=correlation_id,
        mutator=mutator,
    )


def sync_scheduled_payments_slice(owner_id, *, source: str = "", event_type: str = "", correlation_id: str = ""):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return None

    count = _scheduled_payments_active_count_for_user(user)

    def mutator(projection):
        projection.scheduled_payments_active_count = _clamp_non_negative(count)

    return mutate_user_usage_projection(
        user,
        source=source,
        event_type=event_type,
        correlation_id=correlation_id,
        mutator=mutator,
    )


def sync_payments_usage_slice(owner_id, *, reference=None, source: str = "", event_type: str = "", correlation_id: str = ""):
    from django.contrib.auth import get_user_model
    from payments.payment_intents.models import PaymentIntent

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return None

    start, end = month_bounds(reference=reference)
    day_start, day_end = day_bounds(reference=reference)
    payment_qs = PaymentIntent.objects.filter(
        owner=user,
        created_at__gte=start,
        created_at__lt=end,
        status__in=PAYMENT_COUNTABLE_STATUSES,
    )
    payment_qs_day = PaymentIntent.objects.filter(
        owner=user,
        created_at__gte=day_start,
        created_at__lt=day_end,
        status__in=PAYMENT_COUNTABLE_STATUSES,
    )
    total = payment_qs.aggregate(total=Sum("amount"))["total"] or ZERO
    count = payment_qs.count()
    total_day = payment_qs_day.aggregate(total=Sum("amount"))["total"] or ZERO
    count_day = payment_qs_day.count()

    def mutator(projection):
        projection.current_period_start = start
        projection.current_period_end = end
        projection.current_day_start = day_start
        projection.current_day_end = day_end
        projection.payments_count_month = _clamp_non_negative(count)
        projection.payments_volume_month = total
        projection.payments_count_day = _clamp_non_negative(count_day)
        projection.payments_volume_day = total_day

    return mutate_user_usage_projection(
        user,
        source=source,
        event_type=event_type,
        correlation_id=correlation_id,
        mutator=mutator,
    )


def sync_payouts_usage_slice(owner_id, *, reference=None, source: str = "", event_type: str = "", correlation_id: str = ""):
    from django.contrib.auth import get_user_model
    from payments.payment_intents.models import PayoutInstruction

    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return None

    start, end = month_bounds(reference=reference)
    day_start, day_end = day_bounds(reference=reference)
    payout_qs = PayoutInstruction.objects.filter(
        batch__owner=user,
        created_at__gte=start,
        created_at__lt=end,
        status__in={
            PayoutInstruction.Status.CREATED,
            PayoutInstruction.Status.DISPATCHED,
            PayoutInstruction.Status.SUCCEEDED,
        },
    )
    payout_qs_day = PayoutInstruction.objects.filter(
        batch__owner=user,
        created_at__gte=day_start,
        created_at__lt=day_end,
        status__in={
            PayoutInstruction.Status.CREATED,
            PayoutInstruction.Status.DISPATCHED,
            PayoutInstruction.Status.SUCCEEDED,
        },
    )
    total = payout_qs.aggregate(total=Sum("amount"))["total"] or ZERO
    count = payout_qs.count()
    total_day = payout_qs_day.aggregate(total=Sum("amount"))["total"] or ZERO
    count_day = payout_qs_day.count()

    def mutator(projection):
        projection.current_period_start = start
        projection.current_period_end = end
        projection.current_day_start = day_start
        projection.current_day_end = day_end
        projection.payouts_count_month = _clamp_non_negative(count)
        projection.payouts_volume_month = total
        projection.payouts_count_day = _clamp_non_negative(count_day)
        projection.payouts_volume_day = total_day

    return mutate_user_usage_projection(
        user,
        source=source,
        event_type=event_type,
        correlation_id=correlation_id,
        mutator=mutator,
    )


def get_user_usage_projection_snapshot(user, *, allow_rebuild: bool = True) -> dict:
    from identity.eventing.models import UserProductUsageProjection

    projection = UserProductUsageProjection.objects.filter(owner=user).first()
    if projection is None and allow_rebuild:
        projection = rebuild_user_usage_projection(
            user,
            source="identity.users.product_usage_projection.bootstrap",
        )

    if projection is None:
        start, end = month_bounds()
        return {
            "usage_version": 1,
            "current_period_start": start.isoformat(),
            "current_period_end": end.isoformat(),
            "current_day_start": day_start.isoformat(),
            "current_day_end": day_end.isoformat(),
            "manual_accounts_count": 0,
            "connected_accounts_count": 0,
            "active_accounts_count": 0,
            "rules_count": 0,
            "ai_used_month": 0,
            "payments_count_month": 0,
            "payments_volume_month": "0.00",
            "payments_count_day": 0,
            "payments_volume_day": "0.00",
            "payouts_count_month": 0,
            "payouts_volume_month": "0.00",
            "payouts_count_day": 0,
            "payouts_volume_day": "0.00",
            "ocr_used_month": 0,
            "scheduled_payments_active_count": 0,
            "shared_memberships_count": 0,
            "last_source": "",
            "last_event_type": "",
            "last_correlation_id": "",
            "refreshed_at": None,
        }

    return projection.as_snapshot()
