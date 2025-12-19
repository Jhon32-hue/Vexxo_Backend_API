from django.db import models
class InvestmentAccount(models.Model):
    owner = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    currency = models.CharField(max_length=10, default="COP")
