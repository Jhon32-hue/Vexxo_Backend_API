from django.conf import settings
from django.db import models


class SharedGoal(models.Model):
    class ContributionPolicy(models.TextChoices):
        MEMBERS = "members", "Active members"
        MANAGERS = "managers", "Owner and accountants"

    goal = models.OneToOneField("goals.Goal", on_delete=models.CASCADE, related_name="shared_configuration")
    team = models.ForeignKey("teams.Team", on_delete=models.PROTECT, related_name="shared_goals")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_shared_goals",
    )
    contribution_policy = models.CharField(
        max_length=16,
        choices=ContributionPolicy.choices,
        default=ContributionPolicy.MEMBERS,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["team", "is_active"])]
