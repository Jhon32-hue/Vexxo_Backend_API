from django.db import models
class Asset(models.Model):
    SYMBOL_TYPE = [("stock","stock"),("etf","etf"),("bond","bond"),("crypto","crypto"),("fund","fund")]
    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=10, choices=SYMBOL_TYPE)
    currency = models.CharField(max_length=10, default="USD")
