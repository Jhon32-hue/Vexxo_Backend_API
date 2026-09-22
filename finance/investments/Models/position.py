from django.conf import settings
from django.db import models
class Position(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey("investments.InvestmentAccount", on_delete=models.CASCADE)
    asset = models.ForeignKey("investments.Asset", on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    avg_cost = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    class Meta: unique_together = ("owner","account","asset")
