from __future__ import annotations

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.internal_auth import assert_internal_token
from finance.transactions.Models import TransactionIntakeBatch
from finance.transactions.Serializers.intake_serializers import (
    TransactionIntakeBatchResponseSerializer,
    TransactionIntakeBatchSerializer,
    TransactionIntakeSingleRowEnvelopeSerializer,
)
from finance.transactions.Serializers.reconciliation_serializers import (
    TransactionReconciliationIssueResolveSerializer,
    TransactionReconciliationIssueResponseSerializer,
)
from finance.transactions.transaction_intake_service import (
    apply_intake_batch,
    receive_intake_batch,
    receive_single_intake_row,
    reconcile_intake_batch,
)
from finance.transactions.transaction_reconciliation_service import resolve_reconciliation_issue
from finance.transactions.Models import TransactionReconciliationIssue


class InternalTransactionsBaseView(APIView):
    permission_classes = [permissions.AllowAny]

    def _request_id(self, request) -> str:
        return str(request.headers.get("X-Request-Id", "") or "").strip()

    def _idempotency_key(self, request) -> str:
        return str(request.headers.get("Idempotency-Key", "") or "").strip()

    def _validate_transport_headers(self, request):
        try:
            assert_internal_token(
                request,
                "TRANSACTIONS_INTAKE_INTERNAL_TOKEN",
                detail="No autorizado para intake interno de transactions.",
            )
        except Exception as exc:
            if hasattr(exc, "detail"):
                return Response({"detail": str(exc.detail)}, status=status.HTTP_403_FORBIDDEN)
            raise
        if not self._request_id(request):
            return Response({"detail": "X-Request-Id es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if not self._idempotency_key(request):
            return Response({"detail": "Idempotency-Key es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        return None


class InternalTransactionIntakeBatchView(InternalTransactionsBaseView):
    def post(self, request):
        header_error = self._validate_transport_headers(request)
        if header_error:
            return header_error
        serializer = TransactionIntakeBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch, created = receive_intake_batch(
            provider=serializer.validated_data["provider"],
            source=serializer.validated_data["source"],
            provider_account_id=serializer.validated_data.get("provider_account_id", ""),
            cursor=serializer.validated_data.get("cursor", ""),
            request_id=self._request_id(request),
            idempotency_key=self._idempotency_key(request),
            rows=serializer.validated_data.get("rows", []),
            raw_summary=serializer.validated_data.get("raw_summary") or {},
        )
        payload = {
            "created": created,
            "batch": TransactionIntakeBatchResponseSerializer(batch).data,
        }
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class InternalTransactionIntakeBatchApplyView(InternalTransactionsBaseView):
    def post(self, request, batch_id: str):
        header_error = self._validate_transport_headers(request)
        if header_error:
            return header_error
        batch = TransactionIntakeBatch.objects.filter(pk=batch_id).first()
        if batch is None:
            return Response({"detail": "Batch de intake no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        result = apply_intake_batch(batch=batch)
        return Response(
            {
                "batch": TransactionIntakeBatchResponseSerializer(result.batch).data,
                "counts": dict(result.counts),
                "total": result.total,
            },
            status=status.HTTP_200_OK,
        )


class InternalTransactionIntakeRowView(InternalTransactionsBaseView):
    def post(self, request):
        header_error = self._validate_transport_headers(request)
        if header_error:
            return header_error
        serializer = TransactionIntakeSingleRowEnvelopeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = receive_single_intake_row(
            provider=serializer.validated_data["provider"],
            source=serializer.validated_data["source"],
            provider_account_id=serializer.validated_data.get("provider_account_id", ""),
            request_id=self._request_id(request),
            idempotency_key=self._idempotency_key(request),
            row=serializer.validated_data["row"],
        )
        return Response(
            {
                "batch": TransactionIntakeBatchResponseSerializer(result.batch).data,
                "counts": dict(result.counts),
                "total": result.total,
            },
            status=status.HTTP_201_CREATED,
        )


class InternalTransactionIntakeReconcileView(InternalTransactionsBaseView):
    def post(self, request):
        header_error = self._validate_transport_headers(request)
        if header_error:
            return header_error
        serializer = TransactionIntakeBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = reconcile_intake_batch(
            provider=serializer.validated_data["provider"],
            source=serializer.validated_data["source"],
            provider_account_id=serializer.validated_data.get("provider_account_id", ""),
            cursor=serializer.validated_data.get("cursor", ""),
            request_id=self._request_id(request),
            idempotency_key=self._idempotency_key(request),
            rows=serializer.validated_data.get("rows", []),
        )
        return Response(
            {
                "batch": TransactionIntakeBatchResponseSerializer(result.batch).data,
                "counts": dict(result.counts),
                "total": result.total,
            },
            status=status.HTTP_200_OK,
        )


class InternalTransactionReconciliationIssueResolveView(InternalTransactionsBaseView):
    def post(self, request, issue_id: str):
        header_error = self._validate_transport_headers(request)
        if header_error:
            return header_error
        issue = (
            TransactionReconciliationIssue.objects.select_related("transaction", "source_link", "resolved_by", "resolution_transaction")
            .filter(pk=issue_id)
            .first()
        )
        if issue is None:
            return Response({"detail": "Issue de reconciliacion no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = TransactionReconciliationIssueResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            resolved_issue = resolve_reconciliation_issue(
                issue=issue,
                action=serializer.validated_data["action"],
                actor=getattr(request, "user", None) if getattr(request, "user", None) and request.user.is_authenticated else None,
                notes=serializer.validated_data.get("notes", ""),
                payload=serializer.validated_data.get("payload") or {},
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TransactionReconciliationIssueResponseSerializer(resolved_issue).data, status=status.HTTP_200_OK)
