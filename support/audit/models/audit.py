from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    """
    Registro central de auditoría explicable para MindWallet.
    """

    class Source(models.TextChoices):
        USER = "USER", "User"
        SYSTEM = "SYSTEM", "System"
        AI = "AI", "AI"
        AUTOMATION = "AUTOMATION", "Automation"

    class Action(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        AUTO_TRIGGER = "AUTO_TRIGGER", "Auto Trigger"
        CALCULATE = "CALCULATE", "Calculate"
        RECOMMEND = "RECOMMEND", "Recommend"

    class Impact(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )

    # Contexto funcional
    module = models.CharField(
        max_length=50,
        help_text="transactions, budgets, alerts, ai, investments, etc."
    )

    action = models.CharField(
        max_length=20,
        choices=Action.choices
    )

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.USER
    )

    impact = models.CharField(
        max_length=10,
        choices=Impact.choices,
        default=Impact.LOW
    )

    # Entidad afectada
    entity = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=64)

    # Explicabilidad
    description = models.TextField(
        blank=True,
        help_text="Descripción humana del evento"
    )

    diff = models.JSONField(
        default=dict,
        blank=True,
        help_text="Cambios estructurados antes/después"
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Contexto adicional (reglas, inputs, modelos, thresholds)"
    )

    ts = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ts"]
        indexes = [
            models.Index(fields=["user", "module"]),
            models.Index(fields=["entity", "entity_id"]),
            models.Index(fields=["action", "source"]),
            models.Index(fields=["ts"]),
        ]

    def __str__(self):
        return f"[{self.module}] {self.action} {self.entity} ({self.source})"
