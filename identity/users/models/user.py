# users/models/user.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class Currency(models.TextChoices):
    COP = "COP", "Peso Colombiano"
    USD = "USD", "Dólar Americano"
    EUR = "EUR", "Euro"
    MXN = "MXN", "Peso Mexicano"
    ARS = "ARS", "Peso Argentino"
    CLP = "CLP", "Peso Chileno"
    PEN = "PEN", "Sol Peruano"
    BRL = "BRL", "Real Brasileño"


class PlanType(models.TextChoices):
    FREE = "free", _("Plan Gratis")
    PLUS = "plus", _("Plan Plus")
    PRO = "pro", _("Plan Pro")


class User(AbstractUser):
    """
    Usuario de Mindwallet.

    Maneja:
    - datos personales
    - moneda base (preferred_currency / base_currency)
    - plan (free / plus / pro)
    - overrides de límites para soporte / admins
    """

    email = models.EmailField(_("Correo electrónico"), unique=True)
    phone_number = models.CharField(
        _("Teléfono / WhatsApp"), max_length=20, blank=True, null=True
    )

    preferred_currency = models.CharField(
        _("Moneda preferida"),
        max_length=10,
        choices=Currency.choices,
        default=Currency.COP,
    )

    # Alias semántico para el frontend
    @property
    def base_currency(self) -> str:
        return self.preferred_currency

    @base_currency.setter
    def base_currency(self, value: str) -> None:
        self.preferred_currency = value

    # Integraciones
    whatsapp_connected = models.BooleanField(
        _("Cuenta WhatsApp vinculada"), default=False
    )
    photo = models.ImageField(
        _("Foto de perfil"), upload_to="users/photos/", blank=True, null=True
    )

    # Plan / suscripción
    plan = models.CharField(
        _("Plan actual"),
        max_length=10,
        choices=PlanType.choices,
        default=PlanType.FREE,
    )

    # Overrides manuales opcionales (para soporte / enterprise)
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

    # Flags de estado
    is_verified = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)

    last_login_ip = models.GenericIPAddressField(
        _("Última IP de login"), blank=True, null=True
    )
    last_seen = models.DateTimeField(_("Última actividad"), blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ================== UTIL ================== #

    def __str__(self) -> str:
        return f"{self.username} ({self.email})"

    def full_name(self) -> str:
        return (f"{self.first_name} {self.last_name}".strip()) or self.username

    def mark_seen(self, request=None) -> None:
        """Actualiza última actividad e IP."""
        self.last_seen = timezone.now()
        if request and hasattr(request, "META"):
            ip = (
                request.META.get("HTTP_X_FORWARDED_FOR")
                or request.META.get("REMOTE_ADDR")
            )
            self.last_login_ip = ip
        self.save(update_fields=["last_seen", "last_login_ip", "updated_at"])

    # ================== MATRIZ DE PLANES ================== #

    def get_plan_config(self) -> dict:
        """
        Lógica centralizada de límites del plan.

        FREE:
            - 1 cuenta activa
            - 20 transacciones/mes por cuenta
            - 1 reporte mensual
            - 1 conexión API (open finance / exchange)
            - 1 cuenta de inversión
            - 2 cuentas compartidas/equipos
            - 2 contactos

        PLUS / PRO amplían límites.
        """

        base_cfg = {
            PlanType.FREE: {
                "max_accounts": 1,
                "max_monthly_tx_per_account": 20,
                "max_monthly_reports": 1,
                "max_api_connections": 1,
                "max_investment_accounts": 1,
                "max_shared_accounts": 2,
                "max_contacts": 2,
                "max_observed_accounts": 2,
            },
            PlanType.PLUS: {
                "max_accounts": 10,
                "max_monthly_tx_per_account": 500,
                "max_monthly_reports": 10,
                "max_api_connections": 5,
                "max_investment_accounts": 5,
                "max_shared_accounts": 10,
                "max_contacts": 100,
                "max_observed_accounts": 10,
            },
            PlanType.PRO: {
                "max_accounts": None,              # sin límite práctico
                "max_monthly_tx_per_account": None,
                "max_monthly_reports": None,
                "max_api_connections": None,
                "max_investment_accounts": None,
                "max_shared_accounts": None,
                "max_contacts": None,
                "max_observed_accounts": None,
            },
        }

        cfg = base_cfg.get(self.plan, base_cfg[PlanType.FREE])

        # Overrides manuales
        if self.max_accounts_override is not None:
            cfg = {**cfg, "max_accounts": self.max_accounts_override}
        if self.max_observed_accounts_override is not None:
            cfg = {**cfg, "max_observed_accounts": self.max_observed_accounts_override}

        return cfg

    # ================== HELPERS DE LÍMITES ================== #

    # ---- Cuentas propias ----
    def can_create_account(self) -> bool:
        from finance.accounts.models.account import Account

        cfg = self.get_plan_config()
        max_accounts = cfg.get("max_accounts")

        if max_accounts is None:
            return True

        active_accounts = Account.objects.filter(owner=self, is_active=True).count()
        return active_accounts < max_accounts

    # ---- Transacciones por cuenta / mes ----
    def can_add_transaction(self, account, when) -> bool:
        """
        Limita transacciones por cuenta y mes (p.ej. 20 en FREE).
        """
        from datetime import date
        from finance.transactions.Models.transacciones import Transaction

        cfg = self.get_plan_config()
        limit = cfg.get("max_monthly_tx_per_account")

        if limit is None:
            return True

        when = when or date.today()
        start = when.replace(day=1)
        if when.month == 12:
            end = when.replace(year=when.year + 1, month=1, day=1)
        else:
            end = when.replace(month=when.month + 1, day=1)

        count = Transaction.objects.filter(
            owner=self,
            account=account,
            date__gte=start,
            date__lt=end,
        ).count()

        return count < limit

    # ---- Reports mensuales ----
    def can_generate_monthly_report(self, when) -> bool:
        """
        Límite de reportes generados por mes.
        Asume un modelo reports.Report.
        """
        from datetime import date

        try:
            from reports.reports.models import Report
        except Exception:
            return True  # si aún no existe, no limitamos

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

        count = Report.objects.filter(
            owner=self,
            created_at__gte=start,
            created_at__lt=end,
        ).count()

        return count < limit

    # ---- Conexiones API / Open Finance ----
    def can_add_api_connection(self) -> bool:
        """
        Limita conexiones tipo open finance / exchange.
        Asume un modelo integrations.FinancialConnection.
        """
        try:
            from integrations.models import FinancialConnection
        except Exception:
            return True

        cfg = self.get_plan_config()
        limit = cfg.get("max_api_connections")
        if limit is None:
            return True

        count = FinancialConnection.objects.filter(owner=self, is_active=True).count()
        return count < limit

    # ---- Cuentas de inversión ----
    def can_add_investment_account(self) -> bool:
        from finance.accounts.models.account import Account, AccountType

        cfg = self.get_plan_config()
        limit = cfg.get("max_investment_accounts")
        if limit is None:
            return True

        current = Account.objects.filter(
            owner=self,
            type=AccountType.INVESTMENT,
            is_active=True,
        ).count()
        return current < limit

    # ---- Equipos / cuentas compartidas ----
    def can_create_shared_or_team(self) -> bool:
        """
        Limita nº de equipos o cuentas compartidas (Membership role=owner).
        """
        try:
            from social.teams.models import Membership
        except Exception:
            return True

        cfg = self.get_plan_config()
        limit = cfg.get("max_shared_accounts")
        if limit is None:
            return True

        count = Membership.objects.filter(user=self, role="owner").count()
        return count < limit

    # ---- Contactos ----
    def can_add_contact(self) -> bool:
        """
        Limita nº de contactos personales (app contacts).
        """
        try:
            from contacts.models import Contact
        except Exception:
            return True

        cfg = self.get_plan_config()
        limit = cfg.get("max_contacts")
        if limit is None:
            return True

        count = Contact.objects.filter(owner=self).count()
        return count < limit

    class Meta:
        verbose_name = _("Usuario")
        verbose_name_plural = _("Usuarios")
        ordering = ["username"]
