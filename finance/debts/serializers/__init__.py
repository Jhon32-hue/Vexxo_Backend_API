from rest_framework import serializers

from finance.debts.models import Debt, DebtInstallment, DebtRestructuring
from finance.debts.services import (
    DebtLifecycleError,
    create_debt,
    create_debt_installment,
    update_debt,
    update_debt_installment,
)


class DebtSerializer(serializers.ModelSerializer):
    total_paid = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    remaining_balance = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = Debt
        fields = "__all__"
        read_only_fields = ("owner", "status", "closed_at", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["vendor"].queryset = self.fields["vendor"].queryset.filter(
                owner=request.user
            )

    def validate_vendor(self, vendor):
        request = self.context.get("request")
        if vendor is not None and (request is None or vendor.owner_id != request.user.id):
            raise serializers.ValidationError("El proveedor no pertenece al usuario autenticado.")
        return vendor

    def create(self, validated_data):
        owner = validated_data.pop("owner", self.context["request"].user)
        try:
            return create_debt(owner=owner, **validated_data)
        except DebtLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

    def update(self, instance, validated_data):
        try:
            return update_debt(
                debt=instance,
                owner=self.context["request"].user,
                changes=validated_data,
            )
        except DebtLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc


class DebtInstallmentSerializer(serializers.ModelSerializer):
    remaining_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = DebtInstallment
        fields = "__all__"
        read_only_fields = (
            "owner",
            "status",
            "paid_amount",
            "paid_date",
            "paid_transaction",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["debt"].queryset = Debt.objects.filter(owner=request.user)
            self.fields["payment_template"].queryset = self.fields[
                "payment_template"
            ].queryset.filter(owner=request.user)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        debt = attrs.get("debt", getattr(self.instance, "debt", None))
        template = attrs.get("payment_template", getattr(self.instance, "payment_template", None))
        if debt is not None and (user is None or debt.owner_id != user.id):
            raise serializers.ValidationError({"debt": "La deuda no pertenece al usuario autenticado."})
        if self.instance is not None and debt is not None and debt.pk != self.instance.debt_id:
            raise serializers.ValidationError(
                {"debt": "Una cuota existente no puede trasladarse a otra deuda."}
            )
        if template is not None and (user is None or template.owner_id != user.id):
            raise serializers.ValidationError(
                {"payment_template": "El pago programado no pertenece al usuario autenticado."}
            )
        if template is not None and template.debt_id not in {None, getattr(debt, "pk", None)}:
            raise serializers.ValidationError(
                {"payment_template": "El pago programado pertenece a otra deuda."}
            )
        return attrs

    def create(self, validated_data):
        owner = validated_data.pop("owner", self.context["request"].user)
        try:
            return create_debt_installment(owner=owner, **validated_data)
        except DebtLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

    def update(self, instance, validated_data):
        try:
            return update_debt_installment(
                installment=instance,
                owner=self.context["request"].user,
                changes=validated_data,
            )
        except DebtLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc


class DebtRestructuringInstallmentSerializer(serializers.Serializer):
    due_date = serializers.DateField()
    amount_due = serializers.DecimalField(max_digits=16, decimal_places=2)
    principal_component = serializers.DecimalField(max_digits=16, decimal_places=2, required=False)
    interest_component = serializers.DecimalField(max_digits=16, decimal_places=2, required=False)


class DebtRestructuringRequestSerializer(serializers.Serializer):
    effective_date = serializers.DateField()
    reason = serializers.CharField(min_length=10, max_length=500)
    new_terms = serializers.JSONField()
    installments = DebtRestructuringInstallmentSerializer(many=True, allow_empty=False)


class DebtRestructuringSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtRestructuring
        fields = (
            "id",
            "debt",
            "effective_date",
            "reason",
            "previous_terms",
            "new_terms",
            "replaced_installment_ids",
            "created_installment_ids",
            "created_at",
        )
        read_only_fields = fields
