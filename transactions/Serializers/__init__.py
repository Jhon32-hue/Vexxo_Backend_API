from decimal import Decimal
from rest_framework import serializers
from django.contrib.auth import get_user_model
from transactions.Models.transacciones import Transaction, Tag, IncomeSource, ScheduledPayment
from transactions.services import account_month_expense_total

User = get_user_model()


class BaseOwnerSerializer(serializers.ModelSerializer):
    """Asegura owner=request.user en create y valida pertenencia en FKs."""
    def _assert_owner(self, obj, field):
        user = self.context["request"].user
        if obj and getattr(obj, "owner_id", None) and obj.owner_id != user.id:
            raise serializers.ValidationError({field: "No pertenece al usuario autenticado."})

    def create(self, validated_data):
        validated_data["owner"] = self.context["request"].user
        return super().create(validated_data)


class TagSerializer(BaseOwnerSerializer):
    class Meta:
        model = Tag
        fields = "__all__"
        read_only_fields = ("owner",)


class IncomeSourceSerializer(BaseOwnerSerializer):
    class Meta:
        model = IncomeSource
        fields = "__all__"
        read_only_fields = ("owner",)


class ScheduledPaymentSerializer(BaseOwnerSerializer):
    class Meta:
        model = ScheduledPayment
        fields = "__all__"
        read_only_fields = ("owner", "created_at")

    def validate(self, attrs):
        for f in ["account", "category", "vendor", "debt", "installment"]:
            self._assert_owner(attrs.get(f), f)
        return attrs


class TransactionSerializer(BaseOwnerSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)

    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = ("owner", "created_at")

    def validate(self, attrs):
        user = self.context["request"].user

        # amount > 0
        amount = attrs.get("amount", getattr(self.instance, "amount", None))
        if amount is None or Decimal(amount) <= 0:
            raise serializers.ValidationError({"amount": "El monto debe ser mayor a 0."})

        # owner-consistency
        for f in ["account", "category", "vendor", "income_source", "debt", "installment", "scheduled_payment"]:
            self._assert_owner(attrs.get(f), f)

        # coherencia category <-> type (si Category tiene campo 'type')
        cat = attrs.get("category")
        tx_type = attrs.get("type", getattr(self.instance, "type", None))
        if cat and hasattr(cat, "type"):
            if tx_type == "expense" and cat.type != "expense":
                raise serializers.ValidationError({"category": "La categoría debe ser de gasto."})
            if tx_type == "income" and cat.type != "income":
                raise serializers.ValidationError({"category": "La categoría debe ser de ingreso."})

        # límite mensual por cuenta (si aplica)
        account = attrs.get("account", getattr(self.instance, "account", None))
        date = attrs.get("date", getattr(self.instance, "date", None))
        if tx_type == "expense" and account and account.monthly_expense_limit and date:
            month_total = account_month_expense_total(account, date)
            projected = month_total + Decimal(amount)
            if projected > Decimal(account.monthly_expense_limit):
                if getattr(account, "lock_on_limit", False):
                    raise serializers.ValidationError({"amount": "Límite mensual de gasto para la cuenta excedido."})
                # Si no bloquea, se permitirá y la señal emitirá una alerta
        return attrs

    def create(self, validated_data):
        tags_data = self.initial_data.get("tags")
        tx = super().create(validated_data)
        if isinstance(tags_data, list):
            tx.tags.set(Tag.objects.filter(owner=tx.owner, id__in=tags_data))
        return tx

    def update(self, instance, validated_data):
        tags_data = self.initial_data.get("tags")
        tx = super().update(instance, validated_data)
        if isinstance(tags_data, list):
            tx.tags.set(Tag.objects.filter(owner=tx.owner, id__in=tags_data))
        return tx
