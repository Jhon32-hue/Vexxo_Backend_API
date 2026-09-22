"""
Serializers de escritura y validacion para `Account`.

Descripcion general:
- valida creacion y actualizacion del agregado con reglas de negocio del modulo

Analisis detallado:
- aqui viven invariantes de input: limites por plan, unicidad funcional,
  compatibilidad entre goal settings, limites de gasto y restricciones sobre
  cuentas con transacciones existentes
- la mutacion real sigue ocurriendo en el modelo/servicios; este modulo cuida
  la frontera HTTP
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
    AccountType,
    AccountVisibility,
    GoalStrategy,
    RiskLevel,
    SharedScopeType,
)
from finance.accounts.services.account_policy_service import validate_account_write_payload
from finance.accounts.serializers.account_serializer_common import ZERO, quantize_money
from finance.fx.models import Currency


class AccountWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            "id",
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
        read_only_fields = ["id"]

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
        value = quantize_money(value, field_label="Saldo inicial", allow_null=False)
        account_type = self.initial_data.get("type") or getattr(self.instance, "type", None)
        if value < ZERO and account_type not in {AccountType.CREDIT, AccountType.LOAN}:
            raise serializers.ValidationError(_("El saldo inicial negativo solo aplica a cuentas credit o loan."))
        return value

    def validate_monthly_expense_limit(self, value):
        value = quantize_money(value, field_label="Limite mensual")
        if value is not None and value < ZERO:
            raise serializers.ValidationError(_("El limite mensual no puede ser negativo."))
        return value

    def validate_daily_expense_limit(self, value):
        value = quantize_money(value, field_label="Limite diario")
        if value is not None and value < ZERO:
            raise serializers.ValidationError(_("El limite diario no puede ser negativo."))
        return value

    def validate_goal_amount(self, value):
        value = quantize_money(value, field_label="Objetivo")
        if value is not None and value < ZERO:
            raise serializers.ValidationError(_("El objetivo no puede ser negativo."))
        return value

    def validate_auto_contribute_amount(self, value):
        value = quantize_money(value, field_label="Aporte automatico")
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
        return validate_account_write_payload(attrs=attrs, instance=instance, owner=owner)
