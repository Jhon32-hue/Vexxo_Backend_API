from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Category(models.Model):
    TYPE_CHOICES = [
        ("income", "Ingreso"),
        ("expense", "Gasto"),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("owner", "name", "type")
        ordering = ["type", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"
