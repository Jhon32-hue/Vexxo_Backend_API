from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TransactionInferenceRequest(models.Model):
    class Source(models.TextChoices):
        VOICE = "voice", _("voz")

    class Status(models.TextChoices):
        QUEUED = "queued", _("en cola")
        PROCESSING = "processing", _("procesando")
        TRANSCRIPTION_FAILED = "transcription_failed", _("transcripcion fallida")
        EXTRACTION_FAILED = "extraction_failed", _("extraccion fallida")
        APPLIED = "applied", _("aplicada")
        PARTIAL = "partial", _("parcial")
        DEAD_LETTER = "dead_letter", _("agotada")
        CANCELED = "canceled", _("cancelada")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transaction_inference_requests")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_transaction_inferences",
    )
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="transaction_inference_requests",
    )
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.VOICE, db_index=True)
    provider = models.CharField(max_length=64, default="voice_ai", db_index=True)
    request_id = models.CharField(max_length=64, db_index=True)
    idempotency_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED, db_index=True)
    audio_object_ref = models.CharField(max_length=512)
    audio_content_type = models.CharField(max_length=128, blank=True, default="")
    audio_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    language = models.CharField(max_length=16, blank=True, default="")
    provider_request_id = models.CharField(max_length=128, blank=True, default="")
    provider_job_id = models.CharField(max_length=128, blank=True, default="")
    provider_correlation_id = models.CharField(max_length=128, blank=True, default="")
    transcript = models.TextField(blank=True, default="")
    transcript_confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    parser_version = models.CharField(max_length=64, blank=True, default="")
    intake_batch = models.ForeignKey(
        "transactions.TransactionIntakeBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inference_requests",
    )
    result_summary = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    normalized_payload = models.JSONField(default=dict, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["requested_by", "requested_at"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["request_id"]),
            models.Index(fields=["provider", "provider_request_id"]),
            models.Index(fields=["account", "requested_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(retry_count__gte=0),
                name="transaction_inference_retry_count_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source}:{self.id} ({self.status})"

    @property
    def processable_statuses(self) -> set[str]:
        return {self.Status.QUEUED}

    @property
    def failure_mutable_statuses(self) -> set[str]:
        return {self.Status.QUEUED, self.Status.PROCESSING}

    def can_start_processing(self) -> bool:
        return self.status in self.processable_statuses

    def can_mark_failed(self) -> bool:
        return self.status in self.failure_mutable_statuses

    def reset_for_retry(self, *, commit: bool = True) -> None:
        self.status = self.Status.QUEUED
        self.retry_count = 0
        self.next_attempt_at = None
        self.last_error = ""
        self.failed_at = None
        self.processing_started_at = None
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "retry_count",
                    "next_attempt_at",
                    "last_error",
                    "failed_at",
                    "processing_started_at",
                    "updated_at",
                ]
            )

    def mark_processing(self, *, provider_job_id: str = "", provider_correlation_id: str = "", commit: bool = True) -> None:
        self.status = self.Status.PROCESSING
        self.processing_started_at = self.processing_started_at or timezone.now()
        self.last_error = ""
        self.failed_at = None
        self.next_attempt_at = None
        if provider_job_id:
            self.provider_job_id = provider_job_id
        if provider_correlation_id:
            self.provider_correlation_id = provider_correlation_id
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "processing_started_at",
                    "last_error",
                    "failed_at",
                    "next_attempt_at",
                    "provider_job_id",
                    "provider_correlation_id",
                    "updated_at",
                ]
            )

    def mark_applied(self, *, batch=None, result_summary: dict | None = None, partial: bool = False, commit: bool = True) -> None:
        self.status = self.Status.PARTIAL if partial else self.Status.APPLIED
        self.intake_batch = batch or self.intake_batch
        self.result_summary = result_summary or {}
        self.applied_at = timezone.now()
        self.failed_at = None
        self.last_error = ""
        self.next_attempt_at = None
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "intake_batch",
                    "result_summary",
                    "applied_at",
                    "failed_at",
                    "last_error",
                    "next_attempt_at",
                    "updated_at",
                ]
            )

    def mark_failed(self, *, status: str, error: str, max_retries: int = 5, commit: bool = True) -> None:
        if status not in {self.Status.TRANSCRIPTION_FAILED, self.Status.EXTRACTION_FAILED}:
            raise ValueError("Estado de falla invalido para inferencia de transaccion.")
        self.retry_count = int(self.retry_count or 0) + 1
        self.last_error = (error or "")[:2000]
        self.failed_at = timezone.now()
        if self.retry_count >= max(1, int(max_retries or 5)):
            self.status = self.Status.DEAD_LETTER
            self.next_attempt_at = None
        else:
            self.status = status
            delay_seconds = min(1800, 2 ** min(self.retry_count, 10))
            self.next_attempt_at = timezone.now() + timezone.timedelta(seconds=delay_seconds)
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "retry_count",
                    "last_error",
                    "failed_at",
                    "next_attempt_at",
                    "updated_at",
                ]
            )

    def mark_canceled(self, *, reason: str = "", commit: bool = True) -> None:
        self.status = self.Status.CANCELED
        self.last_error = reason or ""
        self.next_attempt_at = None
        if commit:
            self.save(update_fields=["status", "last_error", "next_attempt_at", "updated_at"])
