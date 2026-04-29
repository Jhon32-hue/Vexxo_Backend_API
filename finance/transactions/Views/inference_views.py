from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from finance.accounts.models.account import Account
from finance.accounts.services.permission_service import account_scope_for_user
from finance.transactions.Models import TransactionInferenceRequest
from finance.transactions.Serializers.inference_serializers import (
    TransactionInferenceRequestCreateSerializer,
    TransactionInferenceRequestSerializer,
)
from finance.transactions.transaction_inference_service import (
    create_voice_transaction_inference_request,
    retry_transaction_inference_request,
)


class TransactionInferenceRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TransactionInferenceRequestSerializer
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        "status": ["exact"],
        "source": ["exact"],
        "account": ["exact"],
        "requested_at": ["gte", "lte"],
    }
    ordering_fields = ["requested_at", "updated_at", "status"]

    def get_queryset(self):
        account_scope = account_scope_for_user(self.request.user, Account.objects.all())
        return (
            TransactionInferenceRequest.objects.select_related("account", "owner", "requested_by", "intake_batch")
            .prefetch_related("intake_batch__receipts")
            .filter(account__in=account_scope)
            .distinct()
        )

    def get_serializer_class(self):
        if self.action == "create":
            return TransactionInferenceRequestCreateSerializer
        return TransactionInferenceRequestSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_id = str(request.headers.get("X-Request-Id", "") or "").strip()
        idempotency_key = str(request.headers.get("Idempotency-Key", "") or "").strip()
        if not request_id:
            return Response({"detail": "X-Request-Id es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if not idempotency_key:
            return Response({"detail": "Idempotency-Key es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        inference_request, created = create_voice_transaction_inference_request(
            actor=request.user,
            account=serializer.validated_data["account_id"],
            request_id=request_id,
            idempotency_key=idempotency_key,
            audio_object_ref=serializer.validated_data["audio_object_ref"],
            audio_content_type=serializer.validated_data.get("audio_content_type", ""),
            audio_duration_ms=serializer.validated_data.get("audio_duration_ms"),
            language=serializer.validated_data.get("language", ""),
            provider=serializer.validated_data.get("provider") or "voice_ai",
        )
        inference_request.refresh_from_db()
        response_serializer = TransactionInferenceRequestSerializer(inference_request, context=self.get_serializer_context())
        return Response(
            {"created": created, "inference_request": response_serializer.data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        inference_request = self.get_object()
        inference_request = retry_transaction_inference_request(inference_request=inference_request, actor=request.user)
        inference_request.refresh_from_db()
        return Response(
            TransactionInferenceRequestSerializer(inference_request, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )
