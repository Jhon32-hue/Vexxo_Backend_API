from django.db import models
from django.contrib.auth import get_user_model
User = get_user_model()

class Rule(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    pattern = models.CharField(max_length=240, blank=True, default="")  # regex sobre texto
    conditions = models.JSONField(default=dict, blank=True)  # opcional: {"amount_gt":10000,"vendor":"uber"}
    effects = models.JSONField(default=dict, blank=True)     # {"category_id":..,"account_name":"Bancolombia"}
    priority = models.PositiveIntegerField(default=100)
    active = models.BooleanField(default=True)
    class Meta: ordering = ["priority","id"]

