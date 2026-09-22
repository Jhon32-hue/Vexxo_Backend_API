from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Vendor(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    tax_id = models.CharField(max_length=30, blank=True, null=True)  # NIT o identificación tributaria
    address = models.CharField(max_length=200, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("owner", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.tax_id or 'sin NIT'})"


class VendorAlias(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vendor_aliases")
    vendor = models.ForeignKey(
        Vendor,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="aliases",
    )
    normalized_alias = models.CharField(max_length=180)
    display_name = models.CharField(max_length=180)
    source = models.CharField(max_length=64, default="transaction_intake")
    confidence_score = models.PositiveSmallIntegerField(default=50)
    occurrence_count = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-occurrence_count", "normalized_alias"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "normalized_alias"],
                name="uniq_vendor_alias_per_owner",
            ),
        ]
