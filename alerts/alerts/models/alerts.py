from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AlertType(models.TextChoices):
    LOW_BALANCE = "low_balance", _("Saldo bajo")
    OVER_SPEND = "over_spend", _("Límite de gasto superado")
    UNUSUAL_ACTIVITY = "unusual_activity", _("Actividad inusual")
    SCHEDULED_PAYMENT_DUE = "scheduled_payment_due", _("Pago programado próximo")
    AI_INSIGHT = "ai_insight", _("Insight inteligente")
    SYSTEM = "system", _("Sistema / integraciones")
    GENERIC = "generic", _("Alerta genérica")


class AlertCategory(models.TextChoices):
    SPENDING = "spending", _("Gasto y presupuesto")
    CASHFLOW = "cashflow", _("Flujo de caja")
    DEBT = "debt", _("Deudas y cuotas")
    WEALTH = "wealth", _("Wealth / inversiones")
    SYSTEM = "system", _("Sistema y conexiones")
    AI_INSIGHT = "ai_insight", _("Insights de IA")


class AlertSeverity(models.TextChoices):
    INFO = "info", _("Información")
    WARNING = "warning", _("Advertencia")
    CRITICAL = "critical", _("Crítica")


class AlertStatus(models.TextChoices):
    NEW = "new", _("Nueva")
    ACK = "ack", _("Reconocida")
    SNOOZED = "snoozed", _("Pospuesta")
    RESOLVED = "resolved", _("Resuelta")


class Alert(models.Model):
    """
    Alerta generada por el motor de reglas + IA de Mindwallet.

    Es el objeto base para:
    - alertas de saldo / gasto,
    - recordatorios de pagos,
    - actividad sospechosa,
    - insights de IA (CFO virtual).
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alerts",
    )

    type = models.CharField(
        max_length=40,
        choices=AlertType.choices,
        help_text=_("Tipo lógico de alerta (low_balance, over_spend, etc.)."),
    )

    category = models.CharField(
        max_length=32,
        choices=AlertCategory.choices,
        default=AlertCategory.SPENDING,
        help_text=_("Categoría funcional de la alerta (gasto, deuda, IA, etc.)."),
    )

    severity = models.CharField(
        max_length=16,
        choices=AlertSeverity.choices,
        default=AlertSeverity.INFO,
        help_text=_("Nivel de severidad de la alerta."),
    )

    status = models.CharField(
        max_length=16,
        choices=AlertStatus.choices,
        default=AlertStatus.NEW,
        help_text=_("Estado del ciclo de vida de la alerta."),
    )

    title = models.CharField(
        max_length=180,
        help_text=_("Título corto para mostrar en la UI."),
    )

    message = models.TextField(
        help_text=_("Mensaje descriptivo para el usuario."),
    )

    # Datos de negocio específicos (ids de cuentas, montos, etc.)
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Datos adicionales para contexto (account_id, totals, etc.)."),
    )

    # Metadatos técnicos
    source = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("Módulo / servicio que generó la alerta."),
    )

    correlation_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("ID de correlación para trazar cadenas de eventos."),
    )

    # ===== Campos pensados para IA / scoring =====
    risk_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Score de riesgo estimado (0-100, opcional)."),
    )

    ai_summary = models.TextField(
        blank=True,
        default="",
        help_text=_("Resumen amigable generado por IA sobre esta alerta."),
    )

    ai_tags = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Etiquetas / clasificaciones sugeridas por IA."),
    )

    # ===== Estado de lectura / resolución =====
    is_active = models.BooleanField(
        default=True,
        help_text=_("Si está activa. Al resolverla puede marcarse como False."),
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Fecha en que el usuario marcó como leída la alerta."),
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Fecha en que la alerta se considera resuelta."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["owner", "type"]),
            models.Index(fields=["owner", "severity"]),
            models.Index(fields=["owner", "category"]),
            models.Index(fields=["owner", "status"]),
        ]
        verbose_name = _("Alerta")
        verbose_name_plural = _("Alertas")

    def __str__(self) -> str:
        return f"[{self.severity}/{self.status}] {self.title} -> {self.owner}"

    # ===== Métodos de dominio =====

    def mark_read(self, commit: bool = True):
        from django.utils import timezone

        if self.read_at is None:
            self.read_at = timezone.now()
            if self.status == AlertStatus.NEW:
                self.status = AlertStatus.ACK
            if commit:
                self.save(update_fields=["read_at", "status", "updated_at"])

    def mark_resolved(self, commit: bool = True):
        from django.utils import timezone

        if self.resolved_at is None:
            self.resolved_at = timezone.now()
        self.is_active = False
        self.status = AlertStatus.RESOLVED
        if commit:
            self.save(update_fields=["resolved_at", "is_active", "status", "updated_at"])

    def snooze(self, until, commit: bool = True):
        """
        Futuro: se puede guardar 'snoozed_until' en payload o en otro campo.
        Por ahora solo marca el status.
        """
        self.status = AlertStatus.SNOOZED
        if commit:
            self.save(update_fields=["status", "updated_at"])
        # Se peude guardar until en payload["snoozed_until"]
        self.payload.setdefault("snoozed_until", str(until))
        if commit:
            self.save(update_fields=["payload", "updated_at"])
