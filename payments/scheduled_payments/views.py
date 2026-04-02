"""
API de planificacion para `payments.scheduled_payments`.
"""

from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from payments.payment_intents.models import PaymentIntent
from payments.payment_intents.serializers import PaymentIntentSerializer
from payments.scheduled_payments.models import PaymentScheduleRun, PaymentTemplate
from payments.scheduled_payments.serializers import (
    PaymentIntentFromScheduleSerializer,
    PaymentScheduleRunRequestSerializer,
    PaymentScheduleRunSerializer,
    PaymentTemplateFromIntentSerializer,
    PaymentTemplateSerializer,
)
from payments.scheduled_payments.services import (
    create_payment_intent_from_schedule_run,
    create_payment_template,
    create_template_from_payment_intent,
    request_payment_schedule_run,
    update_payment_template,
)


class PaymentTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentTemplateSerializer

    def get_queryset(self):
        return PaymentTemplate.objects.filter(owner=self.request.user).order_by("name", "id")

    def perform_create(self, serializer):
        instance = create_payment_template(owner=self.request.user, **serializer.validated_data)
        serializer.instance = instance

    def perform_update(self, serializer):
        instance = update_payment_template(serializer.instance, **serializer.validated_data)
        serializer.instance = instance

    @action(detail=True, methods=["post"], url_path="request-run")
    def request_run(self, request, pk=None):
        serializer = PaymentScheduleRunRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = request_payment_schedule_run(
            template=self.get_object(),
            scheduled_for=serializer.validated_data["scheduled_for"],
            run_payload=serializer.validated_data.get("run_payload") or {},
        )
        return Response(PaymentScheduleRunSerializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="from-intent")
    def create_from_intent(self, request):
        serializer = PaymentTemplateFromIntentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment_intent = PaymentIntent.objects.filter(pk=serializer.validated_data["payment_intent_id"], owner=request.user).first()
        if payment_intent is None:
            return Response({"detail": "PaymentIntent no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        template = create_template_from_payment_intent(
            payment_intent,
            cadence=serializer.validated_data["cadence"],
            interval_count=serializer.validated_data["interval_count"],
        )
        return Response(PaymentTemplateSerializer(template).data, status=status.HTTP_201_CREATED)


class PaymentScheduleRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentScheduleRunSerializer

    def get_queryset(self):
        return PaymentScheduleRun.objects.filter(owner=self.request.user).select_related("template", "payment_intent").order_by("-scheduled_for", "-id")

    @action(detail=True, methods=["post"], url_path="materialize-intent")
    def materialize_intent(self, request, pk=None):
        serializer = PaymentIntentFromScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = self.get_object()
        intent = create_payment_intent_from_schedule_run(
            run,
            amount=serializer.validated_data.get("amount"),
            provider=serializer.validated_data.get("provider", ""),
            rail=serializer.validated_data.get("rail", ""),
        )
        return Response(PaymentIntentSerializer(intent).data, status=status.HTTP_200_OK)
