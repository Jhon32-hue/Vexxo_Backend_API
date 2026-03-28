from django.conf import settings
from django.db import models
class Goal(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2)
    target_date = models.DateField()
    account = models.ForeignKey("accounts.Account", on_delete=models.SET_NULL, null=True, blank=True)
    progress = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    strategy = models.JSONField(default=dict, blank=True)  # aportes, interés, inflación
    active = models.BooleanField(default=True)

