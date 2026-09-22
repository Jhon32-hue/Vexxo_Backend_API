from django.db import models


class DocumentMetadata(models.Model):
    document = models.OneToOneField(
        "files.DocumentFile",
        on_delete=models.CASCADE,
        related_name="document_metadata",
    )
    capture_source = models.CharField(max_length=32, blank=True, default="upload")
    captured_at = models.DateTimeField(null=True, blank=True)
    merchant_hint = models.CharField(max_length=180, blank=True, default="")
    amount_hint = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    currency_hint = models.CharField(max_length=12, blank=True, default="")
    attributes = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"metadata:{self.document_id}"
