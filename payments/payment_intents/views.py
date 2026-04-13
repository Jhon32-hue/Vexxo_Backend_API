"""
API y endpoints internos del bounded context `payments.payment_intents`.
"""

from __future__ import annotations

from rest_framework import mixins, status, viewsets, views
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from common.internal_auth import assert_internal_token
from payments.payment_intents.adapters import ADAPTERS, get_payment_provider_adapter
from payments.payment_intents.callback_service import process_payment_provider_callback
from payments.payment_intents.models import (
    PaymentDomainEventOutbox,
    PaymentIntent,
    PaymentOperationalCase,
    PaymentProviderCallbackReceipt,
    PaymentSettlementRecord,
    PayoutBatch,
)
from payments.payment_intents.pricing_service import calculate_embedded_payment_pricing
from payments.payment_intents.payout_service import create_payout_batch
from payments.payment_intents.serializers import (
    PaymentDomainEventOutboxSerializer,
    PaymentIntentCreateSerializer,
    PaymentIntentSerializer,
    PaymentOperationalCaseSerializer,
    PaymentPricingPreviewSerializer,
    PaymentProviderCallbackReceiptSerializer,
    PaymentProviderCallbackSerializer,
    PaymentSettlementRecordSerializer,
    PaymentWorkerReportSerializer,
    PayoutBatchCreateSerializer,
    PayoutBatchSerializer,
)
from payments.payment_intents.services import (
    create_payment_intent,
    mark_payment_intent_cancelled,
    mark_payment_intent_dispatched,
    mark_payment_intent_disputed,
    mark_payment_intent_failed,
    mark_payment_intent_processing,
    mark_payment_intent_requires_action,
    mark_payment_intent_reversed,
    mark_payment_intent_settled,
    mark_payment_intent_succeeded,
    record_payment_provider_reference,
)


class PaymentIntentViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PaymentIntentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            PaymentIntent.objects.filter(owner=self.request.user)
            .select_related("account", "category", "vendor")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return PaymentIntentCreateSerializer
        return super().get_serializer_class()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment_intent = create_payment_intent(user=request.user, **serializer.validated_data)
        return Response(PaymentIntentSerializer(payment_intent).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="pricing-preview")
    def pricing_preview(self, request):
        serializer = PaymentPricingPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = calculate_embedded_payment_pricing(
            user=request.user,
            amount=serializer.validated_data["amount"],
            provider=serializer.validated_data["provider"],
            rail=serializer.validated_data["rail"],
            country=serializer.validated_data.get("country", "CO"),
            payment_type=serializer.validated_data.get("payment_type", PaymentIntent.PaymentType.OTHER),
        )
        return Response(payload, status=status.HTTP_200_OK)


class PayoutBatchViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PayoutBatchSerializer

    def get_queryset(self):
        return PayoutBatch.objects.filter(owner=self.request.user).prefetch_related("instructions").order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return PayoutBatchCreateSerializer
        return super().get_serializer_class()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = create_payout_batch(user=request.user, **serializer.validated_data)
        return Response(PayoutBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class PaymentProviderCallbackView(views.APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, provider: str = "", *args, **kwargs):
        request_payload = request.data
        resolved_provider = str(provider or "").strip()
        if resolved_provider:
            serializer = PaymentProviderCallbackSerializer(
                data={
                    "provider": resolved_provider,
                    "payload": request_payload,
                }
            )
        else:
            serializer = PaymentProviderCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = process_payment_provider_callback(
            provider=serializer.validated_data["provider"],
            payload=serializer.validated_data["payload"],
            headers=dict(request.headers),
        )
        return Response(result, status=status.HTTP_200_OK if result.get("applied") else status.HTTP_202_ACCEPTED)


class PaymentProviderContractView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, provider: str = "", *args, **kwargs):
        if provider:
            adapter = get_payment_provider_adapter(provider)
            return Response(adapter.describe_contract(), status=status.HTTP_200_OK)
        providers = []
        for provider_code in sorted(ADAPTERS.keys()):
            providers.append(get_payment_provider_adapter(provider_code).describe_contract())
        return Response({"providers": providers}, status=status.HTTP_200_OK)


class PaymentWorkerReportView(views.APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def _assert_internal_worker_token(self, request) -> None:
        assert_internal_token(
            request,
            "PAYMENTS_INTERNAL_TOKEN",
            detail="Unauthorized",
        )

    def post(self, request, *args, **kwargs):
        self._assert_internal_worker_token(request)
        serializer = PaymentWorkerReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment_intent = PaymentIntent.objects.filter(pk=serializer.validated_data["payment_intent_id"]).first()
        if payment_intent is None:
            return Response({"detail": "PaymentIntent no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        provider_metadata = serializer.validated_data.get("provider_metadata") or {}
        provider_reference = serializer.validated_data.get("provider_reference", "")
        provider_cus = serializer.validated_data.get("provider_cus", "")
        if provider_reference or provider_cus:
            record_payment_provider_reference(
                payment_intent,
                provider_reference=provider_reference,
                provider_cus=provider_cus,
                provider_metadata=provider_metadata,
            )

        status_value = serializer.validated_data["status"]
        if status_value == PaymentIntent.Status.DISPATCHED:
            payment_intent = mark_payment_intent_dispatched(
                payment_intent,
                provider_intent_id=serializer.validated_data.get("provider_intent_id", ""),
                provider_metadata=provider_metadata,
            )
        elif status_value == PaymentIntent.Status.PROCESSING:
            payment_intent = mark_payment_intent_processing(payment_intent, provider_metadata=provider_metadata)
        elif status_value == PaymentIntent.Status.REQUIRES_ACTION:
            payment_intent = mark_payment_intent_requires_action(payment_intent, provider_metadata=provider_metadata)
        elif status_value == PaymentIntent.Status.SUCCEEDED:
            payment_intent = mark_payment_intent_succeeded(
                payment_intent,
                provider_intent_id=serializer.validated_data.get("provider_intent_id", ""),
                provider_metadata=provider_metadata,
            )
        elif status_value == PaymentIntent.Status.SETTLED:
            payment_intent = mark_payment_intent_settled(payment_intent, provider_metadata=provider_metadata)
        elif status_value == PaymentIntent.Status.FAILED:
            payment_intent = mark_payment_intent_failed(
                payment_intent,
                failure_code=serializer.validated_data.get("failure_code", ""),
                failure_message=serializer.validated_data.get("failure_message", ""),
                provider_metadata=provider_metadata,
            )
        elif status_value == PaymentIntent.Status.CANCELLED:
            payment_intent = mark_payment_intent_cancelled(
                payment_intent,
                failure_message=serializer.validated_data.get("failure_message", ""),
                provider_metadata=provider_metadata,
            )
        elif status_value == PaymentIntent.Status.REVERSED:
            payment_intent = mark_payment_intent_reversed(
                payment_intent,
                failure_message=serializer.validated_data.get("failure_message", ""),
                provider_metadata=provider_metadata,
            )
        elif status_value == PaymentIntent.Status.DISPUTED:
            payment_intent = mark_payment_intent_disputed(
                payment_intent,
                failure_message=serializer.validated_data.get("failure_message", ""),
                provider_metadata=provider_metadata,
            )

        return Response(PaymentIntentSerializer(payment_intent).data, status=status.HTTP_200_OK)


class PaymentDomainEventOutboxViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PaymentDomainEventOutboxSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentDomainEventOutbox.objects.filter(
            payload__owner_id=str(self.request.user.pk)
        ).order_by("-occurred_at")


class PaymentProviderCallbackReceiptViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PaymentProviderCallbackReceiptSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentProviderCallbackReceipt.objects.select_related("payment_intent").filter(
            payment_intent__owner=self.request.user
        ).order_by("-created_at")


class PaymentSettlementRecordViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PaymentSettlementRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentSettlementRecord.objects.select_related("payment_intent").filter(
            payment_intent__owner=self.request.user
        ).order_by("-recorded_at")


class PaymentOperationalCaseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PaymentOperationalCaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentOperationalCase.objects.select_related("payment_intent").filter(
            payment_intent__owner=self.request.user
        ).order_by("-opened_at")
