from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from finance.debts.models import Debt, DebtInstallment
from finance.debts.serializers import (
    DebtInstallmentSerializer,
    DebtRestructuringRequestSerializer,
    DebtRestructuringSerializer,
    DebtSerializer,
)
from finance.debts.services import (
    DebtLifecycleError,
    delete_debt,
    delete_debt_installment,
    restructure_debt,
)


class DebtViewSet(viewsets.ModelViewSet):
    serializer_class = DebtSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Debt.objects.filter(owner=self.request.user).prefetch_related("installments")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        try:
            delete_debt(debt=instance, owner=self.request.user)
        except DebtLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

    @action(detail=True, methods=["post"], url_path="restructure")
    def restructure(self, request, pk=None):
        debt = self.get_object()
        serializer = DebtRestructuringRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            restructuring, created = restructure_debt(
                debt=debt,
                owner=request.user,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                **serializer.validated_data,
            )
        except DebtLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(
            DebtRestructuringSerializer(restructuring).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

class DebtInstallmentViewSet(viewsets.ModelViewSet):
    serializer_class = DebtInstallmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = DebtInstallment.objects.select_related("debt", "payment_template").filter(
            owner=self.request.user
        )
        debt_id = self.request.query_params.get("debt")
        return queryset.filter(debt_id=debt_id) if debt_id else queryset

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        try:
            delete_debt_installment(installment=instance, owner=self.request.user)
        except DebtLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
