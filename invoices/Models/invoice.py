from django.db import models
from django.contrib.auth import get_user_model
User = get_user_model()

class Invoice(models.Model):
    STATUS = [("received","received"),("parsed","parsed"),("failed","failed"),("confirmed","confirmed")]
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to="invoices/")
    issue_date = models.DateField(null=True, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    vendor = models.ForeignKey("vendors.Vendor", on_delete=models.SET_NULL, null=True, blank=True)
    raw_text = models.TextField(blank=True, default="")
    parsed_fields = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="received")
    created_at = models.DateTimeField(auto_now_add=True)
