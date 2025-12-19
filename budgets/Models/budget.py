from django.db import models
class Budget(models.Model):
    owner = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    month = models.CharField(max_length=7)  # YYYY-MM
    category = models.ForeignKey("categories.Category", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    class Meta: unique_together = ("owner","month","category")
