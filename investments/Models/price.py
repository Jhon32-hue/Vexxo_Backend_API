from django.db import models
class PriceHistory(models.Model):
    asset = models.ForeignKey("investments.Asset", on_delete=models.CASCADE)
    date = models.DateField()
    close = models.DecimalField(max_digits=18, decimal_places=6)
    class Meta: unique_together = ("asset","date")
