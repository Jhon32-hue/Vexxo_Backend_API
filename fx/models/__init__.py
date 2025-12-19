from django.db import models
class FXRate(models.Model):
    base = models.CharField(max_length=3)   # p.ej. COP
    quote = models.CharField(max_length=3)  # p.ej. USD
    date = models.DateField()
    rate = models.DecimalField(max_digits=18, decimal_places=6)
    class Meta: unique_together = ("base","quote","date")

