"""
Serializers de inteligencia derivada para accounts.

Descripcion general:
- exponen snapshots, read models y senales derivadas del modulo de cuentas
- separan claramente el estado operativo de `Account` de la lectura agregada

Analisis detallado:
- estos contratos sirven para dashboards, onboarding financiero, soporte y
  motores de producto
- la informacion aqui mostrada es derivada y explicable; no pretende ser una
  "caja negra" de scoring
"""

from __future__ import annotations

from rest_framework import serializers

from finance.accounts.models import (
    AccountCurrencyExposure,
    AccountOwnerMetrics,
    AccountPortfolioSnapshot,
    AccountProductSignal,
    AccountRiskSnapshot,
    AccountTypeDistribution,
)


class AccountPortfolioSnapshotSerializer(serializers.ModelSerializer):
    primary_account_name = serializers.CharField(source="primary_account.name", read_only=True)

    class Meta:
        model = AccountPortfolioSnapshot
        fields = "__all__"
        read_only_fields = fields


class AccountRiskSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountRiskSnapshot
        fields = "__all__"
        read_only_fields = fields


class AccountProductSignalSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountProductSignal
        fields = "__all__"
        read_only_fields = fields


class AccountOwnerMetricsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountOwnerMetrics
        fields = "__all__"
        read_only_fields = fields


class AccountCurrencyExposureSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountCurrencyExposure
        fields = "__all__"
        read_only_fields = fields


class AccountTypeDistributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountTypeDistribution
        fields = "__all__"
        read_only_fields = fields


class AccountIntelligenceRefreshSerializer(serializers.Serializer):
    force = serializers.BooleanField(required=False, default=True)


class AccountIntelligenceWorkerReportSerializer(serializers.Serializer):
    """
    Callback interno para workers que materializan inteligencia fuera del web app.
    """

    owner_id = serializers.CharField()
    status = serializers.ChoiceField(choices=["started", "completed", "failed"])
    task_name = serializers.CharField(required=False, allow_blank=True, default="")
    result = serializers.CharField(required=False, allow_blank=True, default="")
    error_message = serializers.CharField(required=False, allow_blank=True, default="")
