from django.db import models
from django.db.models import Q


class ScheduledJobState(models.Model):
    class Status(models.TextChoices):
        IDLE = "idle", "Idle"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    job_name = models.CharField(max_length=128, primary_key=True)
    interval_seconds = models.PositiveIntegerField(default=60)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IDLE)
    run_count = models.PositiveBigIntegerField(default=0)
    failure_count = models.PositiveBigIntegerField(default=0)
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_finished_at = models.DateTimeField(null=True, blank=True)
    last_succeeded_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_result = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["job_name"]
        indexes = [models.Index(fields=["status", "next_run_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(interval_seconds__gt=0),
                name="scheduled_job_interval_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.job_name} ({self.status})"
