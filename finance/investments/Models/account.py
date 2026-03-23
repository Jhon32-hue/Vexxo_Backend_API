from django.conf import settings
from django.db import models
class InvestmentAccount(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    currency = models.CharField(max_length=10, default="COP")
