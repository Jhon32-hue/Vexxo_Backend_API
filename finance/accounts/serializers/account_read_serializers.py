"""
Serializers de lectura para el agregado `Account`.

Descripcion general:
- define salidas REST orientadas a listado, detalle y resumen

Analisis detallado:
- estos serializers exponen estado operativo y campos derivados sin mezclar
  reglas de escritura
- son la capa de lectura principal para `cuentas`, overview y consumo de UI
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from finance.accounts.models import Account, AccountOwnership
from finance.accounts.serializers.account_serializer_common import TWOPLACES, ZERO


class AccountListSerializer(serializers.ModelSerializer):
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


class AccountSummarySerializer(serializers.Serializer):
    type = serializers.CharField()
    currency = serializers.CharField()
    status = serializers.CharField()
    total_accounts = serializers.IntegerField()
    total_balance = serializers.DecimalField(max_digits=20, decimal_places=2)


AccountSerializer = AccountDetailSerializer
