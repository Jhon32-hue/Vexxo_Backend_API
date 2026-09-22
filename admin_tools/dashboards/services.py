from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.db.models import Q
from security.query_safety import safe_order_by
from django.utils import timezone

from documents.ocr_requests.models import OcrRequest
from notifications.deliveries.models import NotificationDelivery, NotificationStatus
from payments.payment_intents.models import (
    PaymentOperationalCase,
    PaymentProviderCallbackReceipt,
    PaymentSettlementRecord,
)
from tasks.outbox_registry import OUTBOX_SPECS
from tasks.scheduled.models import ScheduledJobState
from integrations.credentials.models import IntegrationCredential
from security.encryption import encryption_status
from security.models import KeyRotationJob, SecurityAuditEvent, SecurityThrottleBucket


def _outbox_summary():
    result = {}
    for name, spec in OUTBOX_SPECS.items():
        model = spec.model
        fields = {field.name for field in model._meta.get_fields()}
        pending = model.objects.filter(published_at__isnull=True)
        dead_filter = Q()
        if "dead_lettered_at" in fields:
            dead_filter = Q(dead_lettered_at__isnull=False)
            pending = pending.filter(dead_lettered_at__isnull=True)
        elif "dead_letter_at" in fields:
            dead_filter = Q(dead_letter_at__isnull=False)
            pending = pending.filter(dead_letter_at__isnull=True)
        timestamp_field = "created_at" if "created_at" in fields else "occurred_at"
        result[name] = {
            "pending": pending.count(),
            "failed": model.objects.exclude(last_error="").count() if "last_error" in fields else 0,
            "dead_letter": model.objects.filter(dead_filter).count() if dead_filter else 0,
            "oldest_pending": safe_order_by(pending, timestamp_field, allowed_fields={timestamp_field}).values_list(timestamp_field, flat=True).first(),
        }
    return result


def build_operations_snapshot() -> dict:
    scheduler = [
        {
            "job": state.job_name,
            "status": state.status,
            "runs": state.run_count,
            "failures": state.failure_count,
            "next_run_at": state.next_run_at,
            "last_error": state.last_error,
        }
        for state in ScheduledJobState.objects.order_by("job_name")
    ]
    encryption = encryption_status()
    return {
        "generated_at": timezone.now(),
        "outboxes": _outbox_summary(),
        "workers": {
            "documents.ocr": {
                row["status"]: row["total"]
                for row in OcrRequest.objects.values("status").annotate(total=models.Count("pk"))
            },
        },
        "scheduler": scheduler,
        "notifications": {
            "pending": NotificationDelivery.objects.filter(status=NotificationStatus.PENDING).count(),
            "failed": NotificationDelivery.objects.filter(status=NotificationStatus.FAILED).count(),
        },
        "payments": {
            "invalid_callbacks": PaymentProviderCallbackReceipt.objects.filter(signature_valid=False).count(),
            "failed_callbacks": PaymentProviderCallbackReceipt.objects.filter(status=PaymentProviderCallbackReceipt.Status.FAILED).count(),
            "open_cases": PaymentOperationalCase.objects.filter(
                status__in=[PaymentOperationalCase.Status.OPEN, PaymentOperationalCase.Status.INVESTIGATING]
            ).count(),
            "settlement_mismatches": PaymentSettlementRecord.objects.filter(
                status=PaymentSettlementRecord.Status.MISMATCH
            ).count(),
        },
        "api_logs": {
            "source": "stdout_json",
            "lookup_key": "request_id",
            "persisted_in_database": False,
        },
        "security": {
            "encryption_configured": encryption["configured"],
            "active_key_version": encryption["active_version"],
            "active_credentials": IntegrationCredential.objects.filter(status="active").count(),
            "credentials_pending_rotation": IntegrationCredential.objects.exclude(
                key_version=encryption["active_version"]
            ).count() if encryption["active_version"] else IntegrationCredential.objects.count(),
            "active_throttle_blocks": SecurityThrottleBucket.objects.filter(
                blocked_until__gt=timezone.now()
            ).count(),
            "critical_events_24h": SecurityAuditEvent.objects.filter(
                severity=SecurityAuditEvent.Severity.CRITICAL,
                created_at__gte=timezone.now() - timedelta(hours=24),
            ).count(),
            "last_key_rotation_status": KeyRotationJob.objects.values_list("status", flat=True).first(),
        },
    }
