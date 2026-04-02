"""
Vocabulario canonico del agregado `Account`.

Descripcion general:
- centraliza enums del modelo para que dominio, serializers y vistas compartan
  el mismo lenguaje

Analisis detallado:
- estos choices representan contratos de negocio, no solo etiquetas de UI
- moverlos fuera del modelo principal reduce acoplamiento y facilita reuso en
  validaciones, filtros, eventos y proyecciones
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from finance.fx.models import Currency


class AccountType(models.TextChoices):
    CASH = "cash", _("Efectivo")
    BANK = "bank", _("Cuenta Bancaria")
    CREDIT = "credit", _("Tarjeta de Credito")
    WALLET = "wallet", _("Monedero Digital")
    INVESTMENT = "investment", _("Cuenta de Inversion")
    SAVINGS = "savings", _("Cuenta de Ahorros")
    LOAN = "loan", _("Prestamo / Credito")
    BROKERAGE = "brokerage", _("Broker / Trading")
    RETIREMENT = "retirement", _("Retiro / Pension")
    CRYPTO = "crypto", _("Cripto")
    PREPAID = "prepaid", _("Cuenta Prepago")
    JOINT = "joint", _("Cuenta Compartida")
    CUSTODIAL = "custodial", _("Cuenta Custodia")
    OTHER = "other", _("Otro")


class AccountRole(models.TextChoices):
    SPENDING = "spending", _("Gasto diario")
    EMERGENCY = "emergency", _("Fondo de emergencia")
    GOAL_VAULT = "goal_vault", _("Boveda de meta")
    SHARED_POOL = "shared_pool", _("Pool compartido")
    INVEST_PORTFOLIO = "invest_portfolio", _("Portafolio de inversion")
    CREDIT_LINE = "credit_line", _("Linea de credito")
    OBSERVED_ONLY = "observed_only", _("Solo observacion")


class AccountOwnership(models.TextChoices):
    OWNED = "owned", _("Propia")
    SHARED = "shared", _("Compartida")
    OBSERVED = "observed", _("Observada")


class AccountStatus(models.TextChoices):
    ACTIVE = "active", _("Activa")
    ARCHIVED = "archived", _("Archivada")
    CLOSED = "closed", _("Cerrada")
    FROZEN = "frozen", _("Congelada")


class SyncStatus(models.TextChoices):
    IDLE = "idle", _("Sincronizacion inactiva")
    OK = "ok", _("Sincronizacion correcta")
    ERROR = "error", _("Error de sincronizacion")
    RUNNING = "running", _("Sincronizando")
    STALE = "stale", _("Datos desactualizados")


class GoalStrategy(models.TextChoices):
    NONE = "none", _("Sin estrategia")
    WEEKLY = "weekly", _("Aporte semanal")
    MONTHLY = "monthly", _("Aporte mensual")
    ROUND_UP = "round_up", _("Redondeo automatico")
    PERCENT_OF_INCOME = "percent_income", _("Porcentaje de ingresos")
    SMART = "smart", _("Estrategia inteligente")


class RiskLevel(models.TextChoices):
    LOW = "low", _("Bajo")
    NORMAL = "normal", _("Normal")
    HIGH = "high", _("Alto")


class SharedScopeType(models.TextChoices):
    NONE = "none", _("Ninguno")
    GROUP = "group", _("Grupo")
    GOAL = "goal", _("Meta compartida")
    CIRCLE = "circle", _("Circulo")
    TEAM = "team", _("Equipo")


class AccountVisibility(models.TextChoices):
    PRIVATE = "private", _("Privada")
    INTERNAL_SHARED = "internal_shared", _("Compartida internamente")
    PUBLIC_PROFILE = "public_profile", _("Visible en perfil publico")


class AccountDataOrigin(models.TextChoices):
    MANUAL = "manual", _("Declarada manualmente")
    IMPORTED = "imported", _("Importada")
    SYNCED = "synced", _("Sincronizada externamente")
    INFERRED = "inferred", _("Inferida")


class AccountVerificationLevel(models.TextChoices):
    SELF_DECLARED = "self_declared", _("Autodeclarada")
    EXTERNALLY_VERIFIED = "externally_verified", _("Verificada externamente")
    RECONCILED = "reconciled", _("Reconciliada")


class AccountSourcePriority(models.TextChoices):
    USER_DECLARED = "user_declared", _("Declaracion del usuario")
    PROVIDER = "provider", _("Proveedor externo")
    SYSTEM_INFERRED = "system_inferred", _("Inferencia del sistema")


class AccountSensitivityLevel(models.TextChoices):
    NORMAL = "normal", _("Normal")
    SENSITIVE = "sensitive", _("Sensible")
    HIGH = "high", _("Alta sensibilidad")
