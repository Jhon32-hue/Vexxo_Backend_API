from django.db import models
class Alert(models.Model):
    owner = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    type = models.CharField(max_length=40)       # budget_breach, low_balance, invoice_due, etc.
    payload = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

