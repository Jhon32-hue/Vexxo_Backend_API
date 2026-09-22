from django.conf import settings
from django.db import models

from security.validators import validate_safe_metadata


class SupportAccessRecord(models.Model):
    staff_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="support_accesses_performed",
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_accesses_received",
    )
    module = models.CharField(max_length=64, db_index=True)
    action = models.CharField(max_length=32, default="read")
    target_type = models.CharField(max_length=96)
    target_id = models.CharField(max_length=160)
    reason = models.CharField(max_length=500)
    case_reference = models.CharField(max_length=120)
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    safe_metadata = models.JSONField(default=dict, blank=True, validators=[validate_safe_metadata])
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["staff_user", "created_at"]),
            models.Index(fields=["subject_user", "module"]),
            models.Index(fields=["target_type", "target_id"]),
        ]
