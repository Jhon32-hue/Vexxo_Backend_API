from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Goal(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        CANCELED = "canceled", "Canceled"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2)
    target_date = models.DateField()
    account = models.ForeignKey("accounts.Account", on_delete=models.SET_NULL, null=True, blank=True)
    progress = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    strategy = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    active = models.BooleanField(default=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-active", "target_date", "name", "id"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "target_date"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(target_amount__gt=0), name="goal_target_amount_positive"),
            models.CheckConstraint(condition=Q(progress__gte=0), name="goal_progress_non_negative"),
        ]

    @property
    def completion_percentage(self) -> Decimal:
        if not self.target_amount:
            return Decimal("0.00")
        value = (Decimal(self.progress) / Decimal(self.target_amount)) * Decimal("100")
        return min(value, Decimal("100.00")).quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"updated_at"}
        return super().save(*args, **kwargs)


class GoalContribution(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        TRANSACTION = "transaction", "Transaction"
        OPENING_BALANCE = "opening_balance", "Opening balance"
        ADJUSTMENT = "adjustment", "Adjustment"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="goal_contributions",
    )
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="contributions")
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="goal_contributions",
    )
    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goal_contributions",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    contributed_on = models.DateField()
    source = models.CharField(max_length=24, choices=Source.choices, default=Source.MANUAL)
    note = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=160)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-contributed_on", "-created_at", "-id"]
        indexes = [
            models.Index(fields=["owner", "contributed_on"]),
            models.Index(fields=["goal", "reversed_at"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="goal_contribution_amount_positive"),
            models.UniqueConstraint(
                fields=["owner", "idempotency_key"],
                name="goal_contribution_owner_idempotency_unique",
            ),
        ]

    @property
    def is_reversed(self) -> bool:
        return self.reversed_at is not None


class GoalMilestone(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="goal_milestones",
    )
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="milestones")
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2)
    achieved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["target_amount", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(target_amount__gt=0), name="goal_milestone_target_positive"),
            models.UniqueConstraint(
                fields=["goal", "target_amount"],
                name="unique_goal_milestone_target",
            ),
        ]
