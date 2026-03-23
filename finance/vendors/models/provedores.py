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
