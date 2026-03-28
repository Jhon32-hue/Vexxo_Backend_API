from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OwnedModel(TimeStampedModel):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="%(class)s_owner")

    class Meta:
        abstract = True
