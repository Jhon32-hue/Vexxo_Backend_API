"""
Serializers de la API de cuentas financieras.

Descripcion general:
- separa lectura rica, escritura controlada y acciones puntuales del modelo
  `Account`
- expone una capa REST clara para la app de finanzas personales de Vexxo

Analisis detallado:
- `Account` es un agregado grande; por eso la API no debe tratar todos sus
  campos como si fueran editables por el mismo flujo
- los serializers de lectura muestran estado financiero, social y operativo
  sin obligar al frontend a recomponer demasiadas piezas
- los serializers de escritura limitan los campos que realmente deben cambiarse
  por CRUD normal; los cambios de ciclo de vida viven mejor como acciones
  explicitas (`freeze`, `close_account`, `set_primary`, etc.)
- esta capa conserva compatibilidad con campos legacy como `archived`,
  `read_only` y `shared_from_user`, pero ya empuja a que el flujo moderno se
  base en `status`, `ownership`, `shared_scope_*` y `AccountMembership`

Que se puede hacer despues:
- separar aun mas serializers por canal si Vexxo crea una API publica distinta
  a la API interna o mobile-first
- agregar snapshots de patrimonio consolidado y respuestas especializadas para
  dashboards o onboarding financiero
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from finance.accounts.models import (
    Account,
    AccountOwnership,
    AccountRole,
    AccountStatus,
    AccountType,
    AccountVisibility,
    GoalStrategy,
    RiskLevel,
    SharedScopeType,
)
from finance.accounts.domain.guards import account_creation_limit_errors
from finance.fx.models import Currency

ZERO = Decimal("0.00")
TWOPLACES = Decimal("0.01")


def _quantize_money(value, *, field_label: str, allow_null: bool = True):
    if value in (None, ""):
        if allow_null:
            return None
        return ZERO
    try:
        return Decimal(str(value)).quantize(TWOPLACES)
    except (InvalidOperation, TypeError, ValueError):
        raise serializers.ValidationError(_("%(field)s invalido.") % {"field": field_label})


class AccountListSerializer(serializers.ModelSerializer):
    """
    Vista resumida de cuentas para listados y dashboards.
    """

    owner_display_name = serializers.CharField(source="owner.display_name", read_only=True)
    shared_from_display_name = serializers.CharField(source="shared_from_user.display_name", read_only=True)
    current_balance = serializers.SerializerMethodField(read_only=True)
    goal_progress = serializers.SerializerMethodField(read_only=True)
    total_transactions = serializers.IntegerField(read_only=True)
    active_memberships_count = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_closed = serializers.BooleanField(read_only=True)
    is_shared_effective = serializers.SerializerMethodField(read_only=True)
    is_observed_effective = serializers.SerializerMethodField(read_only=True)
    has_external_link = serializers.BooleanField(read_only=True)
    sync_health = serializers.CharField(read_only=True)
    balance_health = serializers.CharField(read_only=True)
    membership_health = serializers.CharField(read_only=True)
    integration_health = serializers.CharField(read_only=True)
    account_operational_health = serializers.CharField(read_only=True)

    class Meta:
        model = Account
        fields = [
            "id",
            "owner",
            "owner_display_name",
            "name",
            "slug",
            "type",
            "role",
            "ownership",
            "status",
            "visibility",
            "currency",
            "balance",
            "current_balance",
            "base_currency",
            "virtual_balance_base",
            "institution",
            "provider",
            "sync_status",
            "data_origin",
            "verification_level",
            "source_priority",
            "sensitivity_level",
            "confidence_score",
            "is_primary",
            "archived",
            "read_only",
            "shared_from_user",
            "shared_from_display_name",
            "shared_scope_type",
            "shared_scope_id",
            "has_external_link",
            "sync_health",
            "balance_health",
            "membership_health",
            "integration_health",
            "account_operational_health",
            "goal_amount",
            "goal_progress",
            "total_transactions",
            "active_memberships_count",
            "is_active",
            "is_closed",
            "is_shared_effective",
            "is_observed_effective",
            "account_version",
            "last_domain_event_at",
            "last_consistent_snapshot_at",
            "last_drift_detected_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_current_balance(self, obj):
        return obj.balance

    def get_goal_progress(self, obj):
        goal_amount = getattr(obj, "goal_amount", None)
        if not goal_amount or Decimal(goal_amount) <= ZERO:
            return None
        try:
            progress = (Decimal(obj.balance) / Decimal(goal_amount)) * Decimal("100.00")
        except (InvalidOperation, ZeroDivisionError):
            return None
        return float(progress.quantize(TWOPLACES))

    def get_is_shared_effective(self, obj):
        return obj.ownership == AccountOwnership.SHARED or bool(obj.shared_scope_id)

    def get_is_observed_effective(self, obj):
        return obj.ownership == AccountOwnership.OBSERVED or bool(obj.read_only)


class AccountDetailSerializer(AccountListSerializer):
    """
    Vista detallada de la cuenta para operaciones financieras y soporte.
    """

    class Meta(AccountListSerializer.Meta):
        fields = AccountListSerializer.Meta.fields + [
            "description",
            "color",
            "icon",
            "display_order",
            "country",
            "external_id",
            "external_mask",
            "external_type",
            "allow_auto_sync",
            "last_sync_at",
            "next_sync_at",
            "last_sync_duration_ms",
            "sync_attempts",
            "sync_error_message",
            "sync_cursor",
            "provider_metadata",
            "initial_balance",
            "last_fx_rate",
            "last_fx_at",
            "closed_at",
            "closed_reason",
            "frozen_at",
            "frozen_reason",
            "monthly_expense_limit",
            "daily_expense_limit",
            "lock_on_limit",
            "risk_level",
            "require_2fa_for_movements",
            "auto_round_savings_enabled",
            "goal_deadline",
            "goal_strategy",
            "auto_contribute_amount",
            "auto_contribute_percent",
            "xp",
            "level",
            "streak_days",
            "last_streak_at",
            "badges",
            "last_activity_at",
            "last_transaction_amount",
            "last_transaction_type",
            "last_balance_change_at",
            "last_balance_change_reason",
            "last_sync_status_at",
        ]


class AccountWriteSerializer(serializers.ModelSerializer):
    """
    Flujo de alta y edicion normal de una cuenta.

    Deja fuera cambios de ciclo de vida y operaciones de reconciliacion, que se
    exponen mejor como acciones especificas.
    """

    class Meta:
        model = Account
        fields = [
            "name",
            "type",
            "role",
            "ownership",
            "visibility",
            "currency",
            "country",
            "institution",
            "description",
            "color",
            "icon",
            "display_order",
            "provider",
            "external_id",
            "external_mask",
            "external_type",
            "allow_auto_sync",
            "initial_balance",
            "base_currency",
            "shared_scope_type",
            "shared_scope_id",
            "monthly_expense_limit",
            "daily_expense_limit",
            "lock_on_limit",
            "risk_level",
            "require_2fa_for_movements",
            "auto_round_savings_enabled",
            "goal_amount",
            "goal_deadline",
            "goal_strategy",
            "auto_contribute_amount",
            "auto_contribute_percent",
        ]

    def validate_name(self, value: str):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError(_("El nombre no puede estar vacio."))
        if len(value) < 2:
            raise serializers.ValidationError(_("El nombre es demasiado corto."))
        if len(value) > 120:
            raise serializers.ValidationError(_("El nombre excede el maximo permitido (120)."))
        return value

    def validate_currency(self, value):
        if value not in Currency.values:
            raise serializers.ValidationError(_("Moneda no soportada."))
        return value

    def validate_type(self, value):
        if value not in AccountType.values:
            raise serializers.ValidationError(_("Tipo de cuenta no soportado."))
        return value

    def validate_role(self, value):
        if value not in AccountRole.values:
            raise serializers.ValidationError(_("Rol de cuenta no soportado."))
        return value

    def validate_ownership(self, value):
        if value not in AccountOwnership.values:
            raise serializers.ValidationError(_("Ownership de cuenta no soportado."))
        return value

    def validate_visibility(self, value):
        if value not in AccountVisibility.values:
            raise serializers.ValidationError(_("Visibilidad de cuenta no soportada."))
        return value

    def validate_shared_scope_type(self, value):
        if value not in SharedScopeType.values:
            raise serializers.ValidationError(_("Scope compartido no soportado."))
        return value

    def validate_risk_level(self, value):
        if value and value not in RiskLevel.values:
            raise serializers.ValidationError(_("Nivel de riesgo invalido."))
        return value

    def validate_goal_strategy(self, value):
        if value and value not in GoalStrategy.values:
            raise serializers.ValidationError(_("Estrategia de objetivo invalida."))
        return value

    def validate_initial_balance(self, value):
        value = _quantize_money(value, field_label="Saldo inicial", allow_null=False)
        account_type = self.initial_data.get("type") or getattr(self.instance, "type", None)
        if value < ZERO and account_type not in {AccountType.CREDIT, AccountType.LOAN}:
            raise serializers.ValidationError(
                _("El saldo inicial negativo solo aplica a cuentas credit o loan.")
            )
        return value

    def validate_monthly_expense_limit(self, value):
        value = _quantize_money(value, field_label="Limite mensual")
        if value is not None and value < ZERO:
            raise serializers.ValidationError(_("El limite mensual no puede ser negativo."))
        return value

    def validate_daily_expense_limit(self, value):
        value = _quantize_money(value, field_label="Limite diario")
        if value is not None and value < ZERO:
            raise serializers.ValidationError(_("El limite diario no puede ser negativo."))
        return value

    def validate_goal_amount(self, value):
        value = _quantize_money(value, field_label="Objetivo")
        if value is not None and value < ZERO:
            raise serializers.ValidationError(_("El objetivo no puede ser negativo."))
        return value

    def validate_auto_contribute_amount(self, value):
        value = _quantize_money(value, field_label="Aporte automatico")
        if value is not None and value < ZERO:
            raise serializers.ValidationError(_("El aporte automatico no puede ser negativo."))
        return value

    def validate_goal_deadline(self, value):
        if value and value < timezone.now().date():
            raise serializers.ValidationError(_("La fecha objetivo no puede estar en el pasado."))
        return value

    def validate_auto_contribute_percent(self, value):
        if value in (None, ""):
            return value
        try:
            normalized = Decimal(str(value)).quantize(Decimal("0.001"))
        except (InvalidOperation, TypeError, ValueError):
            raise serializers.ValidationError(_("Porcentaje de aporte invalido."))

        if normalized < Decimal("0.000") or normalized > Decimal("100.000"):
            raise serializers.ValidationError(_("El porcentaje debe estar entre 0 y 100."))
        return normalized

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        request = self.context.get("request")
        owner = getattr(instance, "owner", None) or getattr(request, "user", None)

        name = attrs.get("name", getattr(instance, "name", None))
        currency = attrs.get("currency", getattr(instance, "currency", None))

        if owner and name and currency:
            qs = Account.objects.filter(owner=owner, name=name, currency=currency)
            if instance:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": _("Ya existe una cuenta con este nombre y moneda para este usuario.")}
                )

        if owner and instance is None:
            creation_errors = account_creation_limit_errors(
                owner,
                account_type=attrs.get("type", AccountType.BANK),
            )
            if creation_errors:
                raise serializers.ValidationError(creation_errors)

        monthly_limit = attrs.get("monthly_expense_limit", getattr(instance, "monthly_expense_limit", None))
        daily_limit = attrs.get("daily_expense_limit", getattr(instance, "daily_expense_limit", None))
        lock_on_limit = attrs.get("lock_on_limit", getattr(instance, "lock_on_limit", False))
        if lock_on_limit and not any(limit is not None and limit > ZERO for limit in (monthly_limit, daily_limit)):
            raise serializers.ValidationError(
                {"lock_on_limit": _("lock_on_limit requiere al menos un limite mayor que cero.")}
            )

        goal_amount = attrs.get("goal_amount", getattr(instance, "goal_amount", None))
        goal_deadline = attrs.get("goal_deadline", getattr(instance, "goal_deadline", None))
        goal_strategy = attrs.get("goal_strategy", getattr(instance, "goal_strategy", GoalStrategy.NONE))
        auto_contribute_amount = attrs.get(
            "auto_contribute_amount",
            getattr(instance, "auto_contribute_amount", None),
        )
        auto_contribute_percent = attrs.get(
            "auto_contribute_percent",
            getattr(instance, "auto_contribute_percent", None),
        )

        if goal_deadline and (goal_amount is None or goal_amount <= ZERO):
            raise serializers.ValidationError(
                {"goal_amount": _("Si defines goal_deadline debes definir goal_amount mayor que cero.")}
            )

        if goal_strategy == GoalStrategy.NONE and any(
            value not in (None, ZERO, Decimal("0.000")) for value in (auto_contribute_amount, auto_contribute_percent)
        ):
            raise serializers.ValidationError(
                {"goal_strategy": _("Si configuras aporte automatico debes elegir una estrategia distinta de none.")}
            )

        shared_scope_type = attrs.get("shared_scope_type", getattr(instance, "shared_scope_type", SharedScopeType.NONE))
        shared_scope_id = attrs.get("shared_scope_id", getattr(instance, "shared_scope_id", ""))
        if shared_scope_type == SharedScopeType.NONE:
            attrs["shared_scope_id"] = ""
        elif not (shared_scope_id or "").strip():
            raise serializers.ValidationError(
                {"shared_scope_id": _("El shared_scope_id es requerido cuando shared_scope_type no es none.")}
            )

        if instance and instance.transactions.exists():
            if "currency" in attrs and attrs["currency"] != instance.currency:
                raise serializers.ValidationError(
                    {"currency": _("No puedes cambiar la moneda de una cuenta que ya tiene transacciones.")}
                )
            if "initial_balance" in attrs and attrs["initial_balance"] != instance.initial_balance:
                raise serializers.ValidationError(
                    {"initial_balance": _("No puedes cambiar el saldo inicial cuando ya existen transacciones.")}
                )

        return attrs


class AccountReasonActionSerializer(serializers.Serializer):
    """
    Serializer reutilizable para acciones de estado.
    """

    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class AccountRecalcSerializer(serializers.Serializer):
    """
    Controla el motivo funcional del recalculo manual.
    """

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=64,
        default="manual_recalc",
    )


class AccountSummarySerializer(serializers.Serializer):
    """
    Salida agregada para dashboards y reportes simples de cuentas.
    """

    type = serializers.CharField()
    currency = serializers.CharField()
    status = serializers.CharField()
    total_accounts = serializers.IntegerField()
    total_balance = serializers.DecimalField(max_digits=20, decimal_places=2)


class AccountExternalLinkSerializer(serializers.Serializer):
    """
    Vincula una cuenta local con un proveedor externo.
    """

    provider = serializers.CharField(max_length=64)
    external_id = serializers.CharField(max_length=255)
    external_type = serializers.CharField(required=False, allow_blank=True, max_length=64)
    external_mask = serializers.CharField(required=False, allow_blank=True, max_length=16)
    provider_metadata = serializers.JSONField(required=False)
    next_sync_at = serializers.DateTimeField(required=False)


class AccountSyncScheduleSerializer(serializers.Serializer):
    """
    Programa el siguiente sync de una cuenta conectada.
    """

    delay_minutes = serializers.IntegerField(required=False, min_value=1, max_value=10080, default=30)
    run_at = serializers.DateTimeField(required=False)


class AccountSyncRunningSerializer(serializers.Serializer):
    """
    Marca el inicio de una corrida de sync externa.
    """

    sync_cursor = serializers.CharField(required=False, allow_blank=True, max_length=255)
    next_sync_at = serializers.DateTimeField(required=False)


class AccountSyncSuccessSerializer(serializers.Serializer):
    """
    Reporta una sincronizacion exitosa desde un worker o servicio externo.
    """

    duration_ms = serializers.IntegerField(required=False, min_value=0, default=0)
    sync_cursor = serializers.CharField(required=False, allow_blank=True, max_length=255)
    next_sync_at = serializers.DateTimeField(required=False)
    provider_metadata = serializers.JSONField(required=False)


class AccountSyncErrorSerializer(serializers.Serializer):
    """
    Reporta un error de sincronizacion y opcionalmente programa reintento.
    """

    message = serializers.CharField(max_length=255)
    retry_in_minutes = serializers.IntegerField(required=False, min_value=1, max_value=10080)
    next_sync_at = serializers.DateTimeField(required=False)


class AccountPlanUsageSerializer(serializers.Serializer):
    """
    Snapshot de limites y uso del modulo accounts.
    """

    plan = serializers.CharField()
    limits = serializers.JSONField()
    usage = serializers.JSONField()


# Compatibilidad con imports previos.
AccountSerializer = AccountDetailSerializer
