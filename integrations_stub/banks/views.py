"""
Endpoints internos stub para integraciones bancarias.

Descripcion general:
- recibe jobs internos de sincronizacion de cuentas
- simula el rol de un futuro `integrations_service` externo
"""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings

from finance.accounts.models import Account
from integrations_stub.banks.services import (
    process_stub_account_intelligence_refresh,
    process_stub_account_sync,
    process_stub_consent_revocation,
)
from integrations_stub.banks.transaction_bridge import (
    process_stub_transactions_reconciliation_resolution,
    process_stub_transactions_sync_batch,
)


class InternalAccountSyncJobSerializer(serializers.Serializer):
    event = serializers.JSONField(required=False)
    account_id = serializers.IntegerField()
    provider = serializers.CharField(required=False, allow_blank=True, max_length=64)
    mode = serializers.ChoiceField(choices=["success", "error", "stale"], default="success", required=False)
    sync_cursor = serializers.CharField(required=False, allow_blank=True, max_length=255)
    next_sync_at = serializers.DateTimeField(required=False)
    duration_ms = serializers.IntegerField(required=False, min_value=0, default=0)
    provider_metadata = serializers.JSONField(required=False)
    message = serializers.CharField(required=False, allow_blank=True, max_length=255)
    retry_in_minutes = serializers.IntegerField(required=False, min_value=1, max_value=10080)


class InternalAccountIntelligenceRefreshSerializer(serializers.Serializer):
    event = serializers.JSONField(required=False)
    owner_id = serializers.CharField(max_length=64)


class InternalConsentRevocationSerializer(serializers.Serializer):
    event = serializers.JSONField(required=False)
    user_id = serializers.CharField(max_length=64)
    provider = serializers.CharField(required=False, allow_blank=True, max_length=64)
    consent_type = serializers.CharField(required=False, allow_blank=True, max_length=64)


class InternalTransactionsSyncBatchSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=64)
    source = serializers.CharField(max_length=64)
    provider_account_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=255)
    rows = serializers.ListField(child=serializers.JSONField(), allow_empty=False)
    raw_summary = serializers.JSONField(required=False)


class InternalTransactionsReconciliationResolutionSerializer(serializers.Serializer):
    issue_id = serializers.IntegerField()
    action = serializers.CharField(max_length=64)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    payload = serializers.JSONField(required=False)


class InternalAccountSyncJobView(APIView):
    permission_classes = [AllowAny]

    def _authorized(self, request) -> bool:
        configured = getattr(settings, "ACCOUNTS_SYNC_INTERNAL_TOKEN", "")
        provided = request.headers.get("X-Vexxo-Internal-Token", "")
        if configured:
            return bool(provided and provided == configured)
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and getattr(user, "is_staff", False))

    def post(self, request):
        if not self._authorized(request):
            return Response({"detail": "No autorizado para sync interno."}, status=status.HTTP_403_FORBIDDEN)

        serializer = InternalAccountSyncJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            account = Account.objects.get(pk=serializer.validated_data["account_id"])
        except Account.DoesNotExist:
            return Response({"detail": "Cuenta no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        try:
            account = process_stub_account_sync(account=account, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Sync interno procesado.",
                "account_id": account.pk,
                "sync_status": account.sync_status,
                "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
                "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None,
            },
            status=status.HTTP_200_OK,
        )


class InternalAccountIntelligenceRefreshView(APIView):
    permission_classes = [AllowAny]

    def _authorized(self, request) -> bool:
        configured = getattr(settings, "ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN", "")
        provided = request.headers.get("X-Vexxo-Internal-Token", "")
        if configured:
            return bool(provided and provided == configured)
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and getattr(user, "is_staff", False))

    def post(self, request):
        if not self._authorized(request):
            return Response(
                {"detail": "No autorizado para refresh interno de inteligencia."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = InternalAccountIntelligenceRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = process_stub_account_intelligence_refresh(**serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Refresh interno de inteligencia procesado.",
                **result,
            },
            status=status.HTTP_200_OK,
        )


class InternalConsentRevocationView(APIView):
    permission_classes = [AllowAny]

    def _authorized(self, request) -> bool:
        configured = getattr(settings, "IDENTITY_CONSENTS_INTERNAL_TOKEN", "")
        provided = request.headers.get("X-Vexxo-Internal-Token", "")
        if configured:
            return bool(provided and provided == configured)
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and getattr(user, "is_staff", False))

    def post(self, request):
        if not self._authorized(request):
            return Response(
                {"detail": "No autorizado para revocacion interna de consentimientos."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = InternalConsentRevocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = process_stub_consent_revocation(**serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Revocacion interna de consentimiento procesada.",
                **result,
            },
            status=status.HTTP_200_OK,
        )


class InternalTransactionsSyncBatchView(APIView):
    permission_classes = [AllowAny]

    def _authorized(self, request) -> bool:
        configured = getattr(settings, "TRANSACTIONS_INTAKE_INTERNAL_TOKEN", "")
        provided = request.headers.get("X-Vexxo-Internal-Token", "")
        if configured:
            return bool(provided and provided == configured)
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and getattr(user, "is_staff", False))

    def post(self, request):
        if not self._authorized(request):
            return Response({"detail": "No autorizado para sync interno de transacciones."}, status=status.HTTP_403_FORBIDDEN)
        request_id = str(request.headers.get("X-Request-Id", "") or "").strip()
        idempotency_key = str(request.headers.get("Idempotency-Key", "") or "").strip()
        if not request_id:
            return Response({"detail": "X-Request-Id es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if not idempotency_key:
            return Response({"detail": "Idempotency-Key es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = InternalTransactionsSyncBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = process_stub_transactions_sync_batch(
                request_id=request_id,
                idempotency_key=idempotency_key,
                **serializer.validated_data,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Sync interno de transacciones procesado.", **result}, status=status.HTTP_200_OK)


class InternalTransactionsReconciliationResolutionView(APIView):
    permission_classes = [AllowAny]

    def _authorized(self, request) -> bool:
        configured = getattr(settings, "TRANSACTIONS_INTAKE_INTERNAL_TOKEN", "")
        provided = request.headers.get("X-Vexxo-Internal-Token", "")
        if configured:
            return bool(provided and provided == configured)
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and getattr(user, "is_staff", False))

    def post(self, request):
        if not self._authorized(request):
            return Response({"detail": "No autorizado para resolucion interna de transacciones."}, status=status.HTTP_403_FORBIDDEN)
        serializer = InternalTransactionsReconciliationResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = process_stub_transactions_reconciliation_resolution(**serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Resolucion interna de reconciliacion procesada.", **result}, status=status.HTTP_200_OK)
