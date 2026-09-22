import uuid

from django.conf import settings
from django.db import models


class ReportSnapshot(models.Model):
    class ReportType(models.TextChoices):
        CASHFLOW = "cashflow", "Cashflow"
        EXPENSES_BY_CATEGORY = "expenses_by_category", "Expenses by category"
        MONTHLY_CLOSE = "monthly_close", "Monthly close"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="report_snapshots")
    report_type = models.CharField(max_length=40, choices=ReportType.choices)
    period_start = models.DateField()
    period_end = models.DateField()
    currency = models.CharField(max_length=3, default="COP")
    timezone_name = models.CharField(max_length=64, default="America/Bogota")
    as_of = models.DateTimeField()
    schema_version = models.PositiveSmallIntegerField(default=1)
    generation_version = models.PositiveIntegerField(default=1)
    generation_reason = models.CharField(max_length=240, blank=True, default="")
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )
    payload = models.JSONField(default=dict)
    payload_sha256 = models.CharField(max_length=64, db_index=True)
    idempotency_key = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["owner", "idempotency_key"], name="unique_owner_report_snapshot_key")]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("Report snapshots are immutable.")
        return super().save(*args, **kwargs)
