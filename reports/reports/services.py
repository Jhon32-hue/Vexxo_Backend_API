from __future__ import annotations

import csv
import hashlib
import io
import json
import secrets
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from finance.transactions.Models import Transaction
from reports.exports.models import ReportExport
from reports.snapshots.models import ReportSnapshot
from security.encryption import decrypt_bytes, encryption_status, encrypt_bytes


def _canonical_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@transaction.atomic
def create_report_snapshot(
    *,
    owner,
    report_type: str,
    period_start,
    period_end,
    currency: str,
    timezone_name: str,
    idempotency_key: str,
    generation_version: int = 1,
    generation_reason: str = "",
    supersedes: ReportSnapshot | None = None,
):
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValidationError({"idempotency_key": "Idempotency-Key es requerido."})
    currency = str(currency or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValidationError({"currency": "La moneda debe usar un codigo ISO 4217 de tres letras."})
    if period_end < period_start:
        raise ValidationError({"period": "El periodo final no puede ser anterior al inicial."})
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError({"timezone": "Zona horaria IANA no valida."})
    existing = ReportSnapshot.objects.filter(owner=owner, idempotency_key=key).first()
    if existing:
        expected = (report_type, period_start, period_end, currency, timezone_name)
        actual = (
            existing.report_type,
            existing.period_start,
            existing.period_end,
            existing.currency,
            existing.timezone_name,
        )
        if actual != expected:
            raise ValidationError({"idempotency_key": "La llave ya fue usada con parametros diferentes."})
        return existing, False
    qs = Transaction.objects.filter(
        owner=owner,
        account__currency=currency,
        date__range=(period_start, period_end),
        status__in=[Transaction.Status.POSTED, Transaction.Status.RECONCILED],
    )
    if report_type == ReportSnapshot.ReportType.CASHFLOW:
        income = qs.filter(type=Transaction.Type.INCOME).aggregate(total=Sum("amount"))["total"] or 0
        expenses = qs.filter(type=Transaction.Type.EXPENSE).aggregate(total=Sum("amount"))["total"] or 0
        payload = {"income": str(income), "expenses": str(expenses), "net": str(income - expenses)}
    elif report_type == ReportSnapshot.ReportType.EXPENSES_BY_CATEGORY:
        payload = {
            "rows": [
                {"category": row["category__name"] or "Uncategorized", "total": str(row["total"])}
                for row in qs.filter(type=Transaction.Type.EXPENSE)
                .values("category__name")
                .annotate(total=Sum("amount"))
                .order_by("-total")
            ]
        }
    elif report_type == ReportSnapshot.ReportType.MONTHLY_CLOSE:
        from finance.budgets.services import build_budget_monthly_overview

        income = qs.filter(type=Transaction.Type.INCOME).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        expenses = qs.filter(type=Transaction.Type.EXPENSE).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        payload = {
            "income": str(income),
            "expenses": str(expenses),
            "net": str(income - expenses),
            "transaction_count": qs.count(),
            "budgets": build_budget_monthly_overview(
                owner=owner,
                month=period_start.strftime("%Y-%m"),
            ),
        }
    else:
        raise ValidationError({"report_type": "Tipo de reporte no soportado."})
    body = {
        "schema_version": 1,
        "report_type": report_type,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "currency": currency,
        "timezone": timezone_name,
        "data": payload,
    }
    snapshot = ReportSnapshot.objects.create(
        owner=owner,
        report_type=report_type,
        period_start=period_start,
        period_end=period_end,
        currency=currency,
        timezone_name=timezone_name,
        as_of=timezone.now(),
        generation_version=generation_version,
        generation_reason=str(generation_reason or "")[:240],
        supersedes=supersedes,
        payload=body,
        payload_sha256=hashlib.sha256(_canonical_bytes(body)).hexdigest(),
        idempotency_key=key,
    )
    return snapshot, True


def queue_report_export(*, owner, snapshot: ReportSnapshot, export_format: str) -> tuple[ReportExport, str]:
    if snapshot.owner_id != owner.pk:
        raise ValidationError({"snapshot": "Snapshot no disponible."})
    if not encryption_status()["configured"]:
        raise ValidationError({"encryption": "Configura el keyring antes de generar exports."})
    if export_format not in {"json", "csv"}:
        raise ValidationError({"format": "Formato no soportado."})
    raw_token = secrets.token_urlsafe(32)
    export = ReportExport.objects.create(
        owner=owner,
        snapshot=snapshot,
        export_format=export_format,
        download_token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
    )
    return export, raw_token


def _render_export(export: ReportExport) -> bytes:
    payload = export.snapshot.payload
    if export.export_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["field", "value"])
    for key, value in payload.get("data", {}).items():
        writer.writerow([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])
    return output.getvalue().encode("utf-8")


def process_report_exports(*, limit: int = 20) -> dict:
    summary = {"processed": 0, "failed": 0, "expired": 0}
    now = timezone.now()
    ReportExport.objects.filter(status=ReportExport.Status.READY, expires_at__lte=now).update(status=ReportExport.Status.EXPIRED)
    for export_id in list(ReportExport.objects.filter(status__in=[ReportExport.Status.PENDING, ReportExport.Status.FAILED]).values_list("pk", flat=True)[:limit]):
        try:
            with transaction.atomic():
                export = ReportExport.objects.select_for_update(skip_locked=True).select_related("snapshot").filter(pk=export_id).first()
                if export is None or export.status not in {ReportExport.Status.PENDING, ReportExport.Status.FAILED}:
                    continue
                export.status = ReportExport.Status.PROCESSING
                export.attempt_count += 1
                export.save(update_fields=["status", "attempt_count", "updated_at"])
            plaintext = _render_export(export)
            ciphertext, envelope = encrypt_bytes(plaintext, aad=f"report-export:{export.pk}")
            with transaction.atomic():
                export = ReportExport.objects.select_for_update().get(pk=export_id)
                export.encrypted_content = ciphertext
                export.encryption_envelope = envelope
                export.plaintext_sha256 = hashlib.sha256(plaintext).hexdigest()
                export.expires_at = timezone.now() + timedelta(hours=24)
                export.status = ReportExport.Status.READY
                export.last_error = ""
                export.save()
            summary["processed"] += 1
        except Exception as exc:
            ReportExport.objects.filter(pk=export_id).update(status=ReportExport.Status.FAILED, last_error=str(exc)[:2000])
            summary["failed"] += 1
    return summary


def purge_report_exports(*, limit: int = 200) -> dict:
    """Cryptographically purge expired/downloaded export bodies, retaining audit metadata."""
    now = timezone.now()
    downloaded_cutoff = now - timedelta(hours=int(getattr(settings, "REPORT_EXPORT_DOWNLOADED_RETENTION_HOURS", 24)))
    expired = ReportExport.objects.filter(status=ReportExport.Status.READY, expires_at__lte=now).update(
        status=ReportExport.Status.EXPIRED,
        download_token_hash="",
    )
    candidates = ReportExport.objects.filter(
        content_purged_at__isnull=True,
        legal_hold=False,
    ).filter(
        models.Q(status=ReportExport.Status.EXPIRED)
        | models.Q(status=ReportExport.Status.DOWNLOADED, downloaded_at__lte=downloaded_cutoff)
    )[:limit]
    purged = 0
    for export in candidates:
        export.encrypted_content = b""
        export.encryption_envelope = {}
        export.download_token_hash = ""
        export.last_error = ""
        export.content_purged_at = now
        export.save(
            update_fields=[
                "encrypted_content",
                "encryption_envelope",
                "download_token_hash",
                "last_error",
                "content_purged_at",
                "updated_at",
            ]
        )
        purged += 1
    return {"expired": expired, "purged": purged}


@transaction.atomic
def consume_report_export(*, export_id, owner, token: str) -> tuple[ReportExport, bytes]:
    export = ReportExport.objects.select_for_update().filter(pk=export_id, owner=owner).first()
    candidate = hashlib.sha256(str(token or "").encode()).hexdigest()
    if not export or export.status != ReportExport.Status.READY or not export.expires_at or export.expires_at <= timezone.now() or not secrets.compare_digest(candidate, export.download_token_hash):
        raise ValidationError({"token": "Export no disponible, usado o expirado."})
    plaintext = decrypt_bytes(bytes(export.encrypted_content), export.encryption_envelope, aad=f"report-export:{export.pk}")
    if hashlib.sha256(plaintext).hexdigest() != export.plaintext_sha256:
        raise ValidationError({"export": "Integridad del export invalida."})
    export.status = ReportExport.Status.DOWNLOADED
    export.downloaded_at = timezone.now()
    export.download_token_hash = ""
    export.save(update_fields=["status", "downloaded_at", "download_token_hash", "updated_at"])
    return export, plaintext
