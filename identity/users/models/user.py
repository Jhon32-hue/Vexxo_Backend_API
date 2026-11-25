"""
Modelo de usuario principal de Vexxo.

Descripcion general:
- concentra identidad y autenticacion base
- guarda configuracion regional y moneda preferida
- define estado operativo, plan y limites de producto

Analisis detallado:
- este modelo no representa solo login; tambien funciona como punto de
  decision para capacidades del producto segun el plan
- metodos como `can_create_account`, `can_add_contact` o
  `can_generate_monthly_report` encapsulan reglas de negocio reutilizables
- `preferred_currency` conecta directamente con el dominio FX y sirve como
  moneda base por defecto para cuentas, dashboards y consolidacion
- los overrides manuales permiten soporte enterprise, growth ops o pruebas
  comerciales sin reconfigurar toda la matriz de planes

La intencion es que las demas apps consulten aqui capacidades del usuario sin
duplicar reglas de plan o de estado.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from finance.fx.models import Currency
from identity.users.domain.plan_matrix import get_plan_capabilities, resolve_plan_code


class PlanType(models.TextChoices):
    FREE = "free", _("Plan Gratis")
    PLUS = "plus", _("Plan Plus (legacy)")
    PRO = "pro", _("Plan Pro")
    ENTERPRISE = "enterprise", _("Plan Enterprise")


class UserStatus(models.TextChoices):
    ACTIVE = "active", _("Activo")
    SUSPENDED = "suspended", _("Suspendido")
    DELETED = "deleted", _("Eliminado")
    PENDING = "pending", _("Pendiente de verificación")


class User(AbstractUser):
    """
    Usuario central de Vexxo.

    Mantiene:
    - identidad base
    - moneda preferida / base
    - plan y límites
    - señales de actividad
    - configuración mínima para mobile-first
    """

    email = models.EmailField(_("Correo electrónico"), unique=True)
    registration_idempotency_key_hash = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    phone_number = models.CharField(
        _("Teléfono / WhatsApp"),
        max_length=20,
        blank=True,
        null=True,
        db_index=True,
    )

    preferred_currency = models.CharField(
        _("Moneda preferida"),
        max_length=10,
        choices=Currency.choices,
        default=Currency.COP,
        db_index=True,
    )

    timezone_name = models.CharField(
        _("Zona horaria"),
        max_length=64,
        default="America/Bogota",
    )

    locale = models.CharField(
        _("Locale"),
        max_length=16,
        default="es_CO",
    )

    photo = models.ImageField(
        _("Foto de perfil"),
        upload_to="users/photos/",
        blank=True,
        null=True,
    )

    whatsapp_connected = models.BooleanField(
        _("Cuenta WhatsApp vinculada"),
        default=False,
    )

    plan = models.CharField(
        _("Plan actual"),
        max_length=16,
        choices=PlanType.choices,
        default=PlanType.FREE,
        db_index=True,
    )

    status = models.CharField(
        _("Estado del usuario"),
        max_length=16,
        choices=UserStatus.choices,
        default=UserStatus.PENDING,
        db_index=True,
    )

    is_verified = models.BooleanField(default=False)
    onboarding_completed = models.BooleanField(default=False)

    last_login_ip = models.GenericIPAddressField(
        _("Última IP de login"),
        blank=True,
        null=True,
    )

    last_seen = models.DateTimeField(
        _("Última actividad"),
        blank=True,
        null=True,
    )

    accepted_terms_version = models.CharField(
        _("Versión términos aceptada"),
        max_length=32,
        blank=True,
        default="",
    )

    accepted_privacy_version = models.CharField(
        _("Versión privacidad aceptada"),
        max_length=32,
        blank=True,
        default="",
    )

    marketing_opt_in = models.BooleanField(default=False)

    # Overrides manuales para soporte / enterprise / growth ops
    max_accounts_override = models.PositiveIntegerField(
        _("Máx. cuentas activas (override)"),
        null=True,
        blank=True,
    )

    max_observed_accounts_override = models.PositiveIntegerField(
        _("Máx. cuentas observadas (override)"),
        null=True,
        blank=True,
    )

    max_contacts_override = models.PositiveIntegerField(
        _("Máx. contactos (override)"),
        null=True,
        blank=True,
    )

    max_api_connections_override = models.PositiveIntegerField(
        _("Máx. conexiones API (override)"),
        null=True,
        blank=True,
    )

    max_monthly_reports_override = models.PositiveIntegerField(
        _("Máx. reportes mensuales (override)"),
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = _("Usuario")
        verbose_name_plural = _("Usuarios")
        ordering = ["username"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["phone_number"]),
            models.Index(fields=["plan"]),
            models.Index(fields=["status"]),
            models.Index(fields=["preferred_currency"]),
        ]

    def __str__(self) -> str:
        return f"{self.username} ({self.email})"

    @property
    def base_currency(self) -> str:
        return self.preferred_currency

    @base_currency.setter
    def base_currency(self, value: str) -> None:
        self.preferred_currency = value

    @property
    def display_name(self) -> str:
        return (f"{self.first_name} {self.last_name}".strip()) or self.username or self.email

    @property
    def is_premium(self) -> bool:
        return self.has_paid_plan

    @property
    def effective_plan(self) -> str:
        return resolve_plan_code(self.plan)

    def full_name(self) -> str:
        return self.display_name

    @property
    def has_paid_plan(self) -> bool:
        return self.effective_plan in {PlanType.PRO, PlanType.ENTERPRISE}

    @property
    def is_plus(self) -> bool:
        return self.plan == PlanType.PLUS

    @property
    def is_pro(self) -> bool:
        return self.effective_plan == PlanType.PRO

    @property
    def is_enterprise(self) -> bool:
        return self.effective_plan == PlanType.ENTERPRISE

    def mark_seen(self, request=None, save: bool = True) -> None:
        self.last_seen = timezone.now()

        if request and hasattr(request, "META"):
            ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR")
            if ip:
                self.last_login_ip = ip.split(",")[0].strip() if "," in ip else ip

        if save:
            self.save(update_fields=["last_seen", "last_login_ip", "updated_at"])

    def get_plan_config(self) -> dict:
        """
        Configuración central del plan.
        Todos los límites del sistema deben salir de aquí o de un servicio que use esta matriz.
        """

        cfg = get_plan_capabilities(self.effective_plan)

        if self.max_accounts_override is not None:
            cfg["max_accounts"] = self.max_accounts_override
            cfg["max_active_accounts"] = self.max_accounts_override
            cfg["max_manual_accounts"] = self.max_accounts_override

        if self.max_observed_accounts_override is not None:
            cfg["max_observed_accounts"] = self.max_observed_accounts_override

        if self.max_contacts_override is not None:
            cfg["max_contacts"] = self.max_contacts_override

        if self.max_api_connections_override is not None:
            cfg["max_api_connections"] = self.max_api_connections_override
            cfg["max_connected_accounts"] = self.max_api_connections_override

        if self.max_monthly_reports_override is not None:
            cfg["max_monthly_reports"] = self.max_monthly_reports_override

        return cfg

    def can_create_account(self) -> bool:
        from finance.accounts.models.account import Account, AccountStatus

        cfg = self.get_plan_config()
        limit = cfg.get("max_manual_accounts", cfg.get("max_active_accounts", cfg.get("max_accounts")))

        if limit is None:
            return True

        current = Account.objects.filter(
            owner=self,
            status__in=[AccountStatus.ACTIVE, AccountStatus.FROZEN],
            provider="",
            external_id="",
        ).count()
        return current < limit

    def can_add_investment_account(self) -> bool:
        from finance.accounts.models.account import Account, AccountStatus, AccountType

        cfg = self.get_plan_config()
        limit = cfg.get("max_investment_accounts")

        if limit is None:
            return True

        current = Account.objects.filter(
            owner=self,
            type__in=[AccountType.INVESTMENT, AccountType.BROKERAGE, AccountType.CRYPTO],
            status__in=[AccountStatus.ACTIVE, AccountStatus.FROZEN],
        ).count()
        return current < limit

    def can_add_api_connection(self) -> bool:
        from finance.accounts.models.account import Account, AccountStatus

        cfg = self.get_plan_config()
        limit = cfg.get("max_connected_accounts", cfg.get("max_api_connections"))

        if limit is None:
            return True

        # This capability limits connected accounts, not provider connections.
        current = (
            Account.objects.filter(owner=self, status__in=[AccountStatus.ACTIVE, AccountStatus.FROZEN])
            .exclude(provider="")
            .exclude(external_id="")
            .count()
        )
        return current < limit

    def can_add_contact(self) -> bool:
        from contacts.models import Contact

        cfg = self.get_plan_config()
        limit = cfg.get("max_contacts")

        if limit is None:
            return True

        current = Contact.objects.filter(owner=self).count()
        return current < limit

    def can_generate_monthly_report(self, when=None) -> bool:
        from datetime import date

        from reports.monthly_reports.models import MonthlyReportClose

        cfg = self.get_plan_config()
        limit = cfg.get("max_monthly_reports")

        if limit is None:
            return True

        when = when or date.today()
        start = when.replace(day=1)
        if when.month == 12:
            end = when.replace(year=when.year + 1, month=1, day=1)
        else:
            end = when.replace(month=when.month + 1, day=1)

        current = MonthlyReportClose.objects.filter(
            owner=self,
            created_at__gte=start,
            created_at__lt=end,
        ).count()

        return current < limit
