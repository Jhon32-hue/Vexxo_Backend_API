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
    PaymentScheduleRunCancelSerializer,
    PaymentScheduleRunPostponeSerializer,
    PaymentScheduleRunRequestSerializer,
    PaymentScheduleRunRetrySerializer,
    PaymentScheduleRunResolveSerializer,
    PaymentScheduleRunSerializer,
    PaymentScheduleRunSkipSerializer,
    PaymentTemplateFromIntentSerializer,
    PaymentTemplateSerializer,
)
from payments.scheduled_payments.services import (
    cancel_schedule_run,
    create_payment_intent_from_schedule_run,
    delete_payment_template,
    create_payment_template,
    create_template_from_payment_intent,
    get_schedule_run_operational_metrics,
    mark_schedule_run_paid,
    postpone_schedule_run,
    request_payment_schedule_run,
    retry_failed_schedule_run,
    skip_schedule_run,
    update_payment_template,
)


def _service_error(message: str):
    return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)


class PaymentTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentTemplateSerializer
    successor_path = "/api/payments/scheduled/programmed-payments/"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        path = getattr(request, "path", "") or ""
        if "/api/payments/scheduled/templates" in path:
            response["X-Vexxo-Deprecated"] = "true"
            response["X-Vexxo-Successor"] = self.successor_path
        return response

    def get_queryset(self):
        return PaymentTemplate.objects.filter(owner=self.request.user).order_by("name", "id")

    def perform_create(self, serializer):
        instance = create_payment_template(
            owner=self.request.user,
            idempotency_key=self.request.headers.get("Idempotency-Key", ""),
            **serializer.validated_data,
        )
        serializer.instance = instance

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except ValueError as exc:
            return _service_error(str(exc))
        response_status = status.HTTP_200_OK if serializer.instance._idempotent_replay else status.HTTP_201_CREATED
        return Response(self.get_serializer(serializer.instance).data, status=response_status)

    def perform_update(self, serializer):
        instance = update_payment_template(serializer.instance, **serializer.validated_data)
        serializer.instance = instance

    def perform_destroy(self, instance):
        delete_payment_template(instance)

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
    successor_path = "/api/payments/scheduled/programmed-payment-runs/"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        path = getattr(request, "path", "") or ""
        if "/api/payments/scheduled/runs" in path:
            response["X-Vexxo-Deprecated"] = "true"
            response["X-Vexxo-Successor"] = self.successor_path
        return response

    def get_queryset(self):
        return (
            PaymentScheduleRun.objects.filter(owner=self.request.user)
            .select_related("template", "payment_intent", "materialized_transaction")
            .order_by("-scheduled_for", "-id")
        )

    @action(detail=False, methods=["get"], url_path="operational-metrics")
    def operational_metrics(self, request):
        return Response(get_schedule_run_operational_metrics(owner=request.user), status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="materialize-intent")
    def materialize_intent(self, request, pk=None):
        serializer = PaymentIntentFromScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = self.get_object()
        try:
            intent = create_payment_intent_from_schedule_run(
                run,
                amount=serializer.validated_data.get("amount"),
                provider=serializer.validated_data.get("provider", ""),
                rail=serializer.validated_data.get("rail", ""),
            )
        except ValueError as exc:
            return _service_error(str(exc))
        return Response(PaymentIntentSerializer(intent).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        serializer = PaymentScheduleRunResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = mark_schedule_run_paid(
                self.get_object(),
                actor=request.user,
                paid_on=serializer.validated_data.get("paid_on"),
                amount=serializer.validated_data.get("amount"),
                notes=serializer.validated_data.get("note", ""),
                paid_outside_vexxo=False,
            )
        except ValueError as exc:
            return _service_error(str(exc))
        return Response(PaymentScheduleRunSerializer(run).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="mark-paid-outside")
    def mark_paid_outside(self, request, pk=None):
        serializer = PaymentScheduleRunResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = mark_schedule_run_paid(
                self.get_object(),
                actor=request.user,
                paid_on=serializer.validated_data.get("paid_on"),
                amount=serializer.validated_data.get("amount"),
                notes=serializer.validated_data.get("note", ""),
                paid_outside_vexxo=True,
            )
        except ValueError as exc:
            return _service_error(str(exc))
        return Response(PaymentScheduleRunSerializer(run).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="postpone")
    def postpone(self, request, pk=None):
        serializer = PaymentScheduleRunPostponeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = postpone_schedule_run(
                self.get_object(),
                new_due_on=serializer.validated_data["new_due_on"],
                actor=request.user,
                note=serializer.validated_data.get("note", ""),
            )
        except ValueError as exc:
            return _service_error(str(exc))
        return Response(PaymentScheduleRunSerializer(run).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="skip")
    def skip(self, request, pk=None):
        serializer = PaymentScheduleRunSkipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = skip_schedule_run(
                self.get_object(),
                actor=request.user,
                note=serializer.validated_data.get("note", ""),
            )
        except ValueError as exc:
            return _service_error(str(exc))
        return Response(PaymentScheduleRunSerializer(run).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        serializer = PaymentScheduleRunCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = cancel_schedule_run(
                self.get_object(),
                actor=request.user,
                note=serializer.validated_data.get("note", ""),
            )
        except ValueError as exc:
            return _service_error(str(exc))
        return Response(PaymentScheduleRunSerializer(run).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request, pk=None):
        serializer = PaymentScheduleRunRetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = retry_failed_schedule_run(
                self.get_object(),
                actor=request.user,
                new_due_on=serializer.validated_data.get("new_due_on"),
                note=serializer.validated_data.get("note", ""),
            )
        except ValueError as exc:
            return _service_error(str(exc))
        return Response(PaymentScheduleRunSerializer(run).data, status=status.HTTP_201_CREATED)
