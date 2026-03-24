"""
Serializers para snapshots de reconciliacion de balance.

Descripcion general:
- exponen lectura y creacion manual de `BalanceSnapshot`
- conectan la API con el servicio de reconciliacion del modulo accounts

Analisis detallado:
- los snapshots no son un CRUD decorativo; representan chequeos operativos de
  consistencia entre el cache incremental y el recomputo desde ledger
- por eso la creacion debe pasar por `create_balance_snapshot()` y no por un
  serializer que permita enviar cualquier drift arbitrario desde el cliente
- esta capa es util para soporte, auditoria y jobs manuales de verificacion

Que se puede hacer despues:
- agregar paginacion/agrupacion por periodos para observabilidad financiera
- exponer diffs de transacciones si Vexxo incorpora reconciliacion explicable
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from finance.accounts.models import Account, BalanceSnapshot
from finance.accounts.services.reconcile_service import DEFAULT_DRIFT_THRESHOLD, create_balance_snapshot


class BalanceSnapshotSerializer(serializers.ModelSerializer):
    """
    Vista de observabilidad de un snapshot de balance.
    """

    account_name = serializers.CharField(source="account.name", read_only=True)
    drift_direction = serializers.CharField(read_only=True)

    class Meta:
        model = BalanceSnapshot
        fields = [
            "id",
            "account",
            "account_name",
            "as_of",
            "balance_cached",
            "balance_recomputed",
            "drift",
            "drift_abs",
            "drift_direction",
            "tx_count",
            "is_consistent",
            "source",
            "note",
            "created_at",
        ]
        read_only_fields = fields


class BalanceSnapshotCreateSerializer(serializers.Serializer):
    """
    Crea un snapshot desde el servicio de reconciliacion.
    """

    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all())
    as_of = serializers.DateTimeField(required=False)
    source = serializers.CharField(required=False, allow_blank=True, max_length=32, default="manual_recheck")
    auto_repair = serializers.BooleanField(required=False, default=False)
    drift_threshold = serializers.DecimalField(
        required=False,
        max_digits=18,
        decimal_places=6,
        default=DEFAULT_DRIFT_THRESHOLD,
    )

    def validate_drift_threshold(self, value):
        try:
            normalized = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise serializers.ValidationError("drift_threshold invalido.")

        if normalized < Decimal("0"):
            raise serializers.ValidationError("drift_threshold no puede ser negativo.")
        return normalized

    def create(self, validated_data):
        return create_balance_snapshot(**validated_data)
