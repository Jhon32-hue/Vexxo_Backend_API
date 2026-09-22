from __future__ import annotations

import calendar
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from reports.monthly_reports.models import MonthlyReportClose
from reports.reports.services import create_report_snapshot
from reports.snapshots.models import ReportSnapshot


def _month_bounds(month: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(f"{str(month).strip()}-01")
    except ValueError:
        raise ValidationError({"month": "month debe usar el formato YYYY-MM."})
    return start, date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])


@transaction.atomic
def close_monthly_report(
    *,
    owner,
    month: str,
    currency: str,
    timezone_name: str,
    regenerate: bool = False,
    reason: str = "",
) -> tuple[MonthlyReportClose, bool]:
    period_start, period_end = _month_bounds(month)
    currency = str(currency or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValidationError({"currency": "La moneda debe usar un codigo ISO 4217 de tres letras."})
    try:
        local_today = timezone.now().astimezone(ZoneInfo(timezone_name)).date()
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError({"timezone": "Zona horaria IANA no valida."})
    if period_end >= local_today:
        raise ValidationError({"month": "Solo se pueden cerrar meses ya terminados."})

    current = (
        MonthlyReportClose.objects.select_for_update()
        .filter(owner=owner, period_start=period_start, currency=currency, is_current=True)
        .select_related("snapshot")
        .first()
    )
    if current and not regenerate:
        return current, False
    reason = str(reason or "").strip()
    if current and len(reason) < 10:
        raise ValidationError({"reason": "Regenerar un cierre requiere un motivo de al menos 10 caracteres."})

    version = (current.version + 1) if current else 1
    snapshot, _created = create_report_snapshot(
        owner=owner,
        report_type=ReportSnapshot.ReportType.MONTHLY_CLOSE,
        period_start=period_start,
        period_end=period_end,
        currency=currency,
        timezone_name=timezone_name,
        idempotency_key=f"monthly-close:{period_start.isoformat()}:{currency}:v{version}",
        generation_version=version,
        generation_reason=reason,
        supersedes=current.snapshot if current else None,
    )
    if current:
        current.is_current = False
        current.status = MonthlyReportClose.Status.SUPERSEDED
        current.save(update_fields=["is_current", "status"])
    close = MonthlyReportClose.objects.create(
        owner=owner,
        period_start=period_start,
        period_end=period_end,
        currency=currency,
        timezone_name=timezone_name,
        version=version,
        snapshot=snapshot,
        supersedes=current,
        regeneration_reason=reason,
        closed_at=timezone.now(),
    )
    return close, True
