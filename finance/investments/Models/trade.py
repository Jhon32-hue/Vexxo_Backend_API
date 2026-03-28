from django.conf import settings
from django.db import models
class Trade(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey("investments.InvestmentAccount", on_delete=models.CASCADE)
    asset = models.ForeignKey("investments.Asset", on_delete=models.CASCADE)
    date = models.DateField()
    side = models.CharField(max_length=4, choices=[("buy","buy"),("sell","sell")])
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    price = models.DecimalField(max_digits=18, decimal_places=6)
    fees = models.DecimalField(max_digits=18, decimal_places=6, default=0)
