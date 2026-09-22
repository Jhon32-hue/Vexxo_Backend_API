import uuid

from django.conf import settings
from django.db import models


class MonthlyReportClose(models.Model):
    class Status(models.TextChoices):
        CLOSED = "closed", "Closed"
        SUPERSEDED = "superseded", "Superseded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="monthly_report_closes",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    currency = models.CharField(max_length=3)
    timezone_name = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CLOSED)
    is_current = models.BooleanField(default=True, db_index=True)
    snapshot = models.OneToOneField(
        "snapshots.ReportSnapshot",
        on_delete=models.PROTECT,
        related_name="monthly_close",
    )
    supersedes = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )
    regeneration_reason = models.CharField(max_length=240, blank=True, default="")
    closed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_start", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "period_start", "currency", "version"],
                name="unique_monthly_report_close_version",
            ),
            models.UniqueConstraint(
                fields=["owner", "period_start", "currency"],
                condition=models.Q(is_current=True),
                name="unique_current_monthly_report_close",
            ),
        ]
        indexes = [models.Index(fields=["owner", "period_start", "currency", "is_current"])]
