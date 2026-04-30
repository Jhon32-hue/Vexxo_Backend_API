"""
Modelos derivados de inteligencia para accounts.

Descripcion general:
- define snapshots y read models resumidos a nivel usuario para el modulo de
  cuentas
- separa el write model `Account` de las proyecciones analiticas y de producto

Analisis detallado:
- `Account` sigue siendo la fuente de verdad operativa de cada cuenta
- estos modelos no reemplazan al agregado; materializan lecturas derivadas que
  sirven para onboarding, segmentacion, health score, partnerships y soporte
- se alimentan desde el propio contexto de `accounts`, usando estado ya
  consolidado del dominio sin esperar a que exista un data warehouse
- el objetivo es que Vexxo pueda responder preguntas tipo "que perfil
  financiero de cuentas tiene este usuario" sin recalcular todo a mano en cada
  request

Que se puede hacer despues:
- historizar snapshots por fecha si Vexxo quiere evolucion temporal completa
- exportar estas proyecciones a analytics o BigQuery
- convertir algunas de estas lecturas en feature store o inputs de modelos
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class AccountPortfolioSnapshot(models.Model):
    owner = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="account_portfolio_snapshot",
    )
    primary_account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    snapshot_version = models.CharField(max_length=32, default="accounts.portfolio.v1")

    total_accounts = models.PositiveIntegerField(default=0)
    active_accounts = models.PositiveIntegerField(default=0)
    primary_accounts = models.PositiveIntegerField(default=0)
    shared_accounts = models.PositiveIntegerField(default=0)
    observed_accounts = models.PositiveIntegerField(default=0)
    external_accounts = models.PositiveIntegerField(default=0)
    investment_accounts = models.PositiveIntegerField(default=0)
    credit_accounts = models.PositiveIntegerField(default=0)
    frozen_accounts = models.PositiveIntegerField(default=0)
    archived_accounts = models.PositiveIntegerField(default=0)
    closed_accounts = models.PositiveIntegerField(default=0)
    idle_accounts = models.PositiveIntegerField(default=0)
    currencies_count = models.PositiveIntegerField(default=0)

    total_cached_balance_in_base = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    counts_by_type = models.JSONField(default=dict, blank=True)
    counts_by_currency = models.JSONField(default=dict, blank=True)
    balances_by_currency = models.JSONField(default=dict, blank=True)
    ownership_distribution = models.JSONField(default=dict, blank=True)

    has_multi_currency_accounts = models.BooleanField(default=False)
    has_external_linked_accounts = models.BooleanField(default=False)
    has_investment_exposure = models.BooleanField(default=False)
    has_credit_products = models.BooleanField(default=False)
    has_shared_financial_behavior = models.BooleanField(default=False)
    has_goal_oriented_accounts = models.BooleanField(default=False)
    has_recurrent_sync_failures = models.BooleanField(default=False)
    has_idle_accounts = models.BooleanField(default=False)
    has_many_small_accounts = models.BooleanField(default=False)
    has_single_dependency_account = models.BooleanField(default=False)

    avg_account_age_days = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    idle_accounts_ratio = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.000"))
    frozen_accounts_ratio = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.000"))
    archived_accounts_ratio = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.000"))
    closed_accounts_ratio = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.000"))

    portfolio_complexity_score = models.PositiveSmallIntegerField(default=0)
    account_diversification_score = models.PositiveSmallIntegerField(default=0)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account portfolio snapshot"
        verbose_name_plural = "Account portfolio snapshots"

    def __str__(self) -> str:
        return f"PortfolioSnapshot(owner={self.owner_id}, total={self.total_accounts})"


class AccountRiskSnapshot(models.Model):
    owner = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="account_risk_snapshot",
    )

    risk_input_version = models.CharField(max_length=32, default="accounts.risk.v1")
    product_mix_score = models.PositiveSmallIntegerField(default=0)
    portfolio_stability_score = models.PositiveSmallIntegerField(default=0)
    sync_reliability_score = models.PositiveSmallIntegerField(default=0)
    external_verification_score = models.PositiveSmallIntegerField(default=0)
    ownership_complexity_score = models.PositiveSmallIntegerField(default=0)
    liquidity_proxy_score = models.PositiveSmallIntegerField(default=0)

    active_credit_accounts = models.PositiveIntegerField(default=0)
    active_investment_accounts = models.PositiveIntegerField(default=0)
    external_linked_accounts = models.PositiveIntegerField(default=0)

    dependency_ratio = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.000"))
    sync_success_ratio = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.000"))
    volatile_exposure_ratio = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.000"))

    is_credit_ready_candidate = models.BooleanField(default=False)
    segment_label = models.CharField(max_length=64, default="starter_financiero")
    supporting_factors = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account risk snapshot"
        verbose_name_plural = "Account risk snapshots"

    def __str__(self) -> str:
        return f"RiskSnapshot(owner={self.owner_id}, segment={self.segment_label})"


class AccountProductSignal(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="account_product_signals",
    )
    signal_code = models.CharField(max_length=64)
    signal_value = models.JSONField(default=dict, blank=True)
    confidence = models.PositiveSmallIntegerField(default=0)
    source = models.CharField(max_length=32, default="accounts")
    evidence = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    generated_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account product signal"
        verbose_name_plural = "Account product signals"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "signal_code"],
                name="unique_account_product_signal_per_owner",
            )
        ]
        indexes = [
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["signal_code", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"ProductSignal(owner={self.owner_id}, code={self.signal_code})"


class AccountOwnerMetrics(models.Model):
    owner = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="account_owner_metrics",
    )

    total_accounts = models.PositiveIntegerField(default=0)
    active_accounts = models.PositiveIntegerField(default=0)
    primary_accounts = models.PositiveIntegerField(default=0)
    shared_accounts = models.PositiveIntegerField(default=0)
    observed_accounts = models.PositiveIntegerField(default=0)
    external_accounts = models.PositiveIntegerField(default=0)
    investment_accounts = models.PositiveIntegerField(default=0)
    credit_accounts = models.PositiveIntegerField(default=0)
    currencies_count = models.PositiveIntegerField(default=0)
    total_cached_balance_in_base = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account owner metrics"
        verbose_name_plural = "Account owner metrics"

    def __str__(self) -> str:
        return f"OwnerMetrics(owner={self.owner_id}, total={self.total_accounts})"


class AccountCurrencyExposure(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="account_currency_exposures",
    )
    currency = models.CharField(max_length=10)
    accounts_count = models.PositiveIntegerField(default=0)
    estimated_total_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    exposure_percentage = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.000"))
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account currency exposure"
        verbose_name_plural = "Account currency exposures"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "currency"],
                name="unique_account_currency_exposure_per_owner",
            )
        ]
        indexes = [models.Index(fields=["owner", "currency"])]

    def __str__(self) -> str:
        return f"CurrencyExposure(owner={self.owner_id}, currency={self.currency})"


class AccountTypeDistribution(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="account_type_distributions",
    )
    account_type = models.CharField(max_length=20)
    accounts_count = models.PositiveIntegerField(default=0)
    total_balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    exposure_percentage = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.000"))
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account type distribution"
        verbose_name_plural = "Account type distributions"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "account_type"],
                name="unique_account_type_distribution_per_owner",
            )
        ]
        indexes = [models.Index(fields=["owner", "account_type"])]

    def __str__(self) -> str:
        return f"TypeDistribution(owner={self.owner_id}, type={self.account_type})"


class AccountIntelligenceDispatchState(models.Model):
    class DispatchBackend(models.TextChoices):
        CLOUD_TASKS = "cloud_tasks", "Cloud Tasks"
        LOCAL_WORKER = "local_worker", "Local worker"

    owner = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="account_intelligence_dispatch_state",
    )
    pending_request = models.BooleanField(default=False)
    request_count = models.PositiveIntegerField(default=0)
    last_requested_at = models.DateTimeField(null=True, blank=True)
    last_enqueued_at = models.DateTimeField(null=True, blank=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_completed_at = models.DateTimeField(null=True, blank=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)
    last_event_type = models.CharField(max_length=128, blank=True, default="")
    last_source = models.CharField(max_length=128, blank=True, default="")
    last_correlation_id = models.CharField(max_length=64, blank=True, default="")
    last_task_name = models.CharField(max_length=255, blank=True, default="")
    last_result = models.CharField(max_length=64, blank=True, default="")
    last_error_message = models.TextField(blank=True, default="")
    dispatch_backend = models.CharField(max_length=32, choices=DispatchBackend.choices, blank=True, default="")
    dispatch_attempt_count = models.PositiveIntegerField(default=0)
    last_dispatch_attempt_at = models.DateTimeField(null=True, blank=True)
    last_dispatch_error = models.TextField(blank=True, default="")
    local_worker_locked_at = models.DateTimeField(null=True, blank=True)
    local_worker_locked_by = models.CharField(max_length=64, blank=True, default="")
    stale_recovery_count = models.PositiveIntegerField(default=0)
    last_recovered_at = models.DateTimeField(null=True, blank=True)
    last_operational_issue = models.CharField(max_length=64, blank=True, default="")
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account intelligence dispatch state"
        verbose_name_plural = "Account intelligence dispatch states"
        indexes = [
            models.Index(fields=["pending_request", "last_requested_at"]),
            models.Index(fields=["dispatch_backend", "pending_request"], name="accintel_dispatch_backend_idx"),
            models.Index(fields=["local_worker_locked_at"], name="accintel_local_worker_lock_idx"),
        ]

    def __str__(self) -> str:
        return f"IntelligenceDispatchState(owner={self.owner_id}, pending={self.pending_request})"
