"""
Serializers operativos para fallbacks del balance incremental.

Descripcion general:
- expone evidencia de degradacion contable y agregados de observabilidad
"""

from __future__ import annotations

from rest_framework import serializers

from finance.accounts.models import AccountBalanceFallback


class AccountBalanceFallbackSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    owner_id = serializers.IntegerField(source="account.owner_id", read_only=True)

    class Meta:
        model = AccountBalanceFallback
        fields = [
            "id",
            "account",
            "account_name",
            "owner_id",
            "transaction_id",
            "reason",
            "source",
            "old_state_present",
            "affected_account_ids",
            "old_balance",
            "new_balance",
            "recalculated",
            "delta",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields
