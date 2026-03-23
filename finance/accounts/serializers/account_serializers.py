from __future__ import annotations

from decimal import Decimal
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from finance.accounts.models.account import Account, AccountType, Currency

ZERO = Decimal("0.00")
TWOPLACES = Decimal("0.01")

# Campos "sensibles" financieros/contables que no deberían tocarse por observadores
OBSERVED_LOCKED_FIELDS = {
    "initial_balance",
    "currency",
    "type",
    "monthly_expense_limit",
    "lock_on_limit",
    "goal_amount",
    "goal_deadline",
    "risk_level",
    "require_2fa_for_movements",
    "auto_round_savings_enabled",
}


class AccountSerializer(serializers.ModelSerializer):
    # Derivados / calculados
    current_balance = serializers.SerializerMethodField(read_only=True)
    total_transactions = serializers.IntegerField(read_only=True)
    is_closed = serializers.BooleanField(read_only=True)
    goal_progress = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Account
        fields = [
            # Identidad
            "id",
            "owner",

            # Datos básicos
            "name",
            "type",
            "currency",

            # Open Finance / integraciones
            "institution",
            "provider",
            "external_id",
            "last_sync_at",
            "sync_status",
            "sync_error_message",
            "allow_auto_sync",

            # Saldos y multimoneda
            "initial_balance",
            "balance",
            "base_currency",
            "virtual_balance_base",
            "current_balance",

            # Estado / visibilidad
            "is_active",
            "is_primary",
            "is_closed",
            "archived",
            "closed_at",
            "closed_reason",

            # Observadas / solo lectura
            "read_only",
            "shared_from_user",

            # Reglas inteligentes de la cuenta
            "monthly_expense_limit",
            "lock_on_limit",
            "risk_level",
            "require_2fa_for_movements",
            "auto_round_savings_enabled",

            # Objetivos de la cuenta (goals-lite)
            "goal_amount",
            "goal_deadline",
            "goal_progress",

            # Auditoría embebida
            "last_activity_at",
            "last_transaction_amount",
            "last_transaction_type",

            # Timestamps
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            # owner lo pone la vista
            "owner",

            # Campos gestionados por integraciones / jobs
            "balance",
            "last_sync_at",
            "sync_status",
            "sync_error_message",
            "virtual_balance_base",

            # Estado derivado
            "is_closed",

            # Observada: el backend controla quién comparte a quién
            "shared_from_user",

            # Auditoría
            "last_activity_at",
            "last_transaction_amount",
            "last_transaction_type",

            # Timestamps
            "created_at",
            "updated_at",
            "closed_at",
        ]

    # ========= REPRESENTACIÓN =========

    def get_current_balance(self, obj):
        """
        Para la mayoría de endpoints usamos el balance persistido
        (recalculado vía signals a partir del ledger).
        """
        return obj.balance

    def get_goal_progress(self, obj):
        """
        % de avance hacia el objetivo asociado a esta cuenta,
        usando el balance actual.
        """
        goal_amount = getattr(obj, "goal_amount", None)
        if not goal_amount or goal_amount <= ZERO:
            return None
        try:
            progress = (Decimal(obj.balance) / Decimal(goal_amount)) * Decimal("100.00")
        except Exception:
            return None
        return float(progress.quantize(TWOPLACES))

    def to_representation(self, instance):
        """
        Optimización ligera:
        - Usa total_transactions anotado en queryset si existe.
        - Expone flags derivados de forma consistente.
        """
        data = super().to_representation(instance)

        annotated_total = getattr(instance, "total_transactions", None)
        if annotated_total is not None:
            data["total_transactions"] = annotated_total
        else:
            data["total_transactions"] = instance.transactions_qs().count()

        data["is_closed"] = instance.is_closed
        return data

    # ========= VALIDACIONES DE CAMPOS =========

    def validate_name(self, value: str):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError(_("El nombre no puede estar vacío."))
        if len(value) < 2:
            raise serializers.ValidationError(_("El nombre es demasiado corto."))
        if len(value) > 120:
            raise serializers.ValidationError(_("El nombre excede el máximo permitido (120)."))

        # Unicidad por owner: (owner, name, currency) la tienes en DB,
        # pero damos error bonito a nivel API.
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            qs = Account.objects.filter(owner=request.user, name=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    _("Ya existe una cuenta con este nombre para este usuario.")
                )
        return value

    def validate_initial_balance(self, value):
        if value is None:
            return ZERO
        try:
            value = Decimal(value).quantize(TWOPLACES)
        except Exception:
            raise serializers.ValidationError(_("Saldo inicial inválido."))

        account_type = None
        if hasattr(self, "initial_data"):
            account_type = self.initial_data.get("type")
        if self.instance and not account_type:
            account_type = self.instance.type

        negative_allowed_types = {"credit", "loan"}
        if value < ZERO and account_type not in negative_allowed_types:
            raise serializers.ValidationError(
                _("El saldo inicial negativo solo está permitido para cuentas 'credit' o 'loan'.")
            )
        return value

    def validate_monthly_expense_limit(self, value):
        if value is None:
            return value
        try:
            value = Decimal(value).quantize(TWOPLACES)
        except Exception:
            raise serializers.ValidationError(_("Límite mensual inválido."))
        if value < ZERO:
            raise serializers.ValidationError(_("El límite mensual no puede ser negativo."))
        return value

    def validate_goal_amount(self, value):
        if value is None:
            return value
        try:
            value = Decimal(value).quantize(TWOPLACES)
        except Exception:
            raise serializers.ValidationError(_("Objetivo inválido."))
        if value < ZERO:
            raise serializers.ValidationError(_("El objetivo no puede ser negativo."))
        return value

    def validate_goal_deadline(self, value):
        if value is None:
            return value
        # regla suave: no metas fechas en pasado (puedes cambiar a "permitir")
        if value < timezone.now().date():
            raise serializers.ValidationError(_("La fecha objetivo no puede estar en el pasado."))
        return value

    def validate_currency(self, value):
        if value not in Currency.values:
            raise serializers.ValidationError(_("Moneda no soportada."))
        return value

    def validate_type(self, value):
        if value not in AccountType.values:
            raise serializers.ValidationError(_("Tipo de cuenta no soportado."))
        return value

    def validate_risk_level(self, value):
        if not value:
            return value
        allowed = {"low", "normal", "high"}
        if value not in allowed:
            raise serializers.ValidationError(_("Nivel de riesgo inválido. Usa: low, normal o high."))
        return value

    def validate_closed_reason(self, value):
        value = (value or "").strip()
        if value and len(value) > 255:
            raise serializers.ValidationError(_("El motivo de cierre excede 255 caracteres."))
        return value

    # ========= VALIDACIONES GLOBALES =========

    def validate(self, attrs):
        """
        Reglas de negocio avanzadas ligadas SOLO a la cuenta.

        Mantiene tu lógica, pero la refuerza con coherencias extra:
        - lock_on_limit requiere monthly_expense_limit
        - goal_deadline requiere goal_amount
        - si read_only está activo, bloquea cambios sensibles para observadores
        """
        instance = getattr(self, "instance", None)
        request = self.context.get("request")
        user = request.user if request else None

        has_instance = instance is not None
        has_transactions = instance.transactions_qs().exists() if has_instance else False

        # ----- 0) coherencias locales -----
        monthly_limit = attrs.get("monthly_expense_limit", getattr(instance, "monthly_expense_limit", None))
        lock_on_limit = attrs.get("lock_on_limit", getattr(instance, "lock_on_limit", False))
        if lock_on_limit and (monthly_limit is None or monthly_limit <= ZERO):
            raise serializers.ValidationError(
                {"monthly_expense_limit": _("Si lock_on_limit=true debes definir monthly_expense_limit > 0.")}
            )

        goal_amount = attrs.get("goal_amount", getattr(instance, "goal_amount", None))
        goal_deadline = attrs.get("goal_deadline", getattr(instance, "goal_deadline", None))
        if goal_deadline and (goal_amount is None or goal_amount <= ZERO):
            raise serializers.ValidationError(
                {"goal_amount": _("Si defines goal_deadline debes definir goal_amount > 0.")}
            )

        # ----- 1) Ledger-safe -----
        if has_instance and "initial_balance" in attrs and has_transactions:
            if attrs["initial_balance"] != instance.initial_balance:
                raise serializers.ValidationError(
                    {"initial_balance": _("No puedes cambiar el saldo inicial cuando ya existen transacciones.")}
                )

        if has_instance and "currency" in attrs and has_transactions:
            if attrs["currency"] != instance.currency:
                raise serializers.ValidationError(
                    {"currency": _("No puedes cambiar la moneda de una cuenta que ya tiene transacciones.")}
                )

        if has_instance and instance.is_closed and attrs.get("is_active") is True:
            raise serializers.ValidationError(
                {"is_active": _("Esta cuenta está cerrada y no puede reabrirse desde esta operación.")}
            )

        if has_instance and attrs.get("is_active") is False:
            if instance.balance != ZERO:
                raise serializers.ValidationError(
                    {"is_active": _("No puedes desactivar/cerrar una cuenta con saldo distinto de cero.")}
                )

        # ----- 2) Archivado / estado -----
        # (tu coherencia suave se mantiene; no forzamos nada)

        # ----- 3) Observadas / read_only (legacy) + Social guard -----
        read_only = attrs.get("read_only", getattr(instance, "read_only", False))
        shared_from_user = getattr(instance, "shared_from_user", None) if has_instance else None

        # Si es cuenta observada: el observador NO puede tocar campos sensibles
        if has_instance and read_only and shared_from_user and user and user != shared_from_user:
            for field in OBSERVED_LOCKED_FIELDS:
                if field in attrs:
                    raise serializers.ValidationError(
                        {field: _("No puedes modificar este campo en una cuenta observada.")}
                    )

        # ----- 4) Goals coherentes (ya validado arriba, se mantiene) -----
        # goal_amount no negativo ya se valida por campo

        return attrs
