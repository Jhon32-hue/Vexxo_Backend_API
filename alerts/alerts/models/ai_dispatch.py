from __future__ import annotations

from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AlertAiDispatchState(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", _("en cola")
        PROCESSING = "processing", _("procesando")
        DISPATCH_FAILED = "dispatch_failed", _("despacho fallido")
        PROCESSING_STALE = "processing_stale", _("procesamiento stale")
        APPLIED = "applied", _("aplicada")
        FAILED = "failed", _("fallida")
        DEAD_LETTER = "dead_letter", _("agotada")

    class DispatchBackend(models.TextChoices):
        CLOUD_TASKS = "cloud_tasks", _("cloud tasks")
        LOCAL_WORKER = "local_worker", _("worker local")

    alert = models.OneToOneField(
        "alerts.Alert",
        on_delete=models.CASCADE,
        related_name="ai_dispatch_state",
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.QUEUED, db_index=True)
    dispatch_backend = models.CharField(
        max_length=32,
        choices=DispatchBackend.choices,
        blank=True,
        default="",
        db_index=True,
    )
    request_count = models.PositiveIntegerField(default=0)
    dispatch_attempt_count = models.PositiveIntegerField(default=0)
    retry_count = models.PositiveIntegerField(default=0)
    stale_recovery_count = models.PositiveIntegerField(default=0)
    last_dispatch_result = models.CharField(max_length=64, blank=True, default="")
    last_dispatch_attempt_at = models.DateTimeField(null=True, blank=True)
    last_dispatch_error = models.TextField(blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    last_operational_issue = models.CharField(max_length=64, blank=True, default="")
    local_worker_locked_at = models.DateTimeField(null=True, blank=True)
    local_worker_locked_by = models.CharField(max_length=64, blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    last_recovered_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["dispatch_backend", "status"]),
            models.Index(fields=["local_worker_locked_at"]),
        ]

    def __str__(self) -> str:
        return f"alert-ai:{self.alert_id} ({self.status})"

    @property
    def processable_statuses(self) -> set[str]:
        return {
            self.Status.QUEUED,
            self.Status.DISPATCH_FAILED,
            self.Status.PROCESSING_STALE,
        }

    def note_dispatch_attempt(self, *, backend: str = "", result: str = "", error: str = "", commit: bool = True) -> None:
        self.dispatch_attempt_count = int(self.dispatch_attempt_count or 0) + 1
        self.last_dispatch_attempt_at = timezone.now()
        self.last_dispatch_result = (result or "")[:64]
        self.last_dispatch_error = (error or "")[:2000]
        if backend:
            self.dispatch_backend = backend
        if not error:
            self.last_dispatch_error = ""
        if commit:
            self.save(
                update_fields=[
                    "dispatch_backend",
                    "dispatch_attempt_count",
                    "last_dispatch_result",
                    "last_dispatch_attempt_at",
                    "last_dispatch_error",
                    "updated_at",
                ]
            )

    def mark_queued(self, *, backend: str = "", commit: bool = True) -> None:
        self.status = self.Status.QUEUED
        self.failed_at = None
        self.processing_started_at = None
        self.next_attempt_at = None
        self.last_error = ""
        self.last_operational_issue = ""
        self.local_worker_locked_at = None
        self.local_worker_locked_by = ""
        if backend:
            self.dispatch_backend = backend
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "failed_at",
                    "processing_started_at",
                    "next_attempt_at",
                    "last_error",
                    "last_operational_issue",
                    "dispatch_backend",
                    "local_worker_locked_at",
                    "local_worker_locked_by",
                    "updated_at",
                ]
            )

    def mark_dispatch_failed(self, *, error: str, backend: str = "", commit: bool = True) -> None:
        self.status = self.Status.DISPATCH_FAILED
        self.failed_at = timezone.now()
        self.last_error = (error or "")[:2000]
        self.last_operational_issue = "dispatch_failed"
        self.next_attempt_at = None
        self.local_worker_locked_at = None
        self.local_worker_locked_by = ""
        if backend:
            self.dispatch_backend = backend
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "failed_at",
                    "last_error",
                    "last_operational_issue",
                    "next_attempt_at",
                    "dispatch_backend",
                    "local_worker_locked_at",
                    "local_worker_locked_by",
                    "updated_at",
                ]
            )

    def mark_processing(self, *, commit: bool = True) -> None:
        self.status = self.Status.PROCESSING
        self.processing_started_at = self.processing_started_at or timezone.now()
        self.failed_at = None
        self.next_attempt_at = None
        self.last_error = ""
        self.last_operational_issue = ""
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "processing_started_at",
                    "failed_at",
                    "next_attempt_at",
                    "last_error",
                    "last_operational_issue",
                    "updated_at",
                ]
            )

    def mark_processing_stale(self, *, reason: str, commit: bool = True) -> None:
        self.status = self.Status.PROCESSING_STALE
        self.failed_at = timezone.now()
        self.last_error = (reason or "")[:2000]
        self.last_operational_issue = "processing_stale"
        self.local_worker_locked_at = None
        self.local_worker_locked_by = ""
        self.next_attempt_at = None
        self.stale_recovery_count = int(self.stale_recovery_count or 0) + 1
        self.last_recovered_at = timezone.now()
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "failed_at",
                    "last_error",
                    "last_operational_issue",
                    "local_worker_locked_at",
                    "local_worker_locked_by",
                    "next_attempt_at",
                    "stale_recovery_count",
                    "last_recovered_at",
                    "updated_at",
                ]
            )

    def mark_applied(self, *, commit: bool = True) -> None:
        self.status = self.Status.APPLIED
        self.applied_at = timezone.now()
        self.failed_at = None
        self.next_attempt_at = None
        self.last_error = ""
        self.last_operational_issue = ""
        self.local_worker_locked_at = None
        self.local_worker_locked_by = ""
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "applied_at",
                    "failed_at",
                    "next_attempt_at",
                    "last_error",
                    "last_operational_issue",
                    "local_worker_locked_at",
                    "local_worker_locked_by",
                    "updated_at",
                ]
            )

    def mark_failed(self, *, error: str, max_retries: int = 3, commit: bool = True) -> None:
        self.retry_count = int(self.retry_count or 0) + 1
        self.failed_at = timezone.now()
        self.last_error = (error or "")[:2000]
        self.local_worker_locked_at = None
        self.local_worker_locked_by = ""
        if self.retry_count >= max(1, int(max_retries or 3)):
            self.status = self.Status.DEAD_LETTER
            self.next_attempt_at = None
            self.last_operational_issue = "dead_letter"
        else:
            self.status = self.Status.FAILED
            self.next_attempt_at = timezone.now() + timezone.timedelta(
                seconds=min(1800, 2 ** min(self.retry_count, 10))
            )
            self.last_operational_issue = "worker_failed"
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "retry_count",
                    "failed_at",
                    "last_error",
                    "next_attempt_at",
                    "last_operational_issue",
                    "local_worker_locked_at",
                    "local_worker_locked_by",
                    "updated_at",
                ]
            )

    def claim_for_local_worker(self, *, worker_id: str, stale_after_seconds: int = 900) -> bool:
        now = timezone.now()
        stale_threshold = now - timezone.timedelta(seconds=max(30, int(stale_after_seconds or 900)))
        with transaction.atomic():
            updated = (
                self.__class__.objects.filter(
                    pk=self.pk,
                    status__in=list(self.processable_statuses),
                )
                .filter(models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=now))
                .filter(
                    models.Q(local_worker_locked_at__isnull=True)
                    | models.Q(local_worker_locked_at__lte=stale_threshold)
                )
                .update(
                    local_worker_locked_at=now,
                    local_worker_locked_by=(worker_id or "")[:64],
                    dispatch_backend=self.DispatchBackend.LOCAL_WORKER,
                )
            )
        if not updated:
            return False
        self.local_worker_locked_at = now
        self.local_worker_locked_by = (worker_id or "")[:64]
        self.dispatch_backend = self.DispatchBackend.LOCAL_WORKER
        return True
