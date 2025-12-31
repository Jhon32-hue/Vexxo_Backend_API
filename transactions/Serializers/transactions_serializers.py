# transactions/Serializers/transactions_serializers.py
from decimal import Decimal

from rest_framework import serializers
from django.contrib.auth import get_user_model

from transactions.Models.transacciones import (
    Transaction,
    Tag,
    IncomeSource,
    ScheduledPayment,
)
from transactions.utils_limits import account_month_expense_total, user_month_tx_count

User = get_user_model()


class BaseOwnerSerializer(serializers.ModelSerializer):
    """Asegura owner=request.user en create y valida pertenencia en FKs."""

    def _assert_owner(self, obj, field):
        user = self.context["request"].user
        if obj and getattr(obj, "owner_id", None) and obj.owner_id != user.id:
            raise serializers.ValidationError(
                {field: "No pertenece al usuario autenticado."}
            )

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
        # Aseguramos pertenencia en FKs
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
        read_only_fields = ("owner", "created_at", "updated_at", "fingerprint")

    # ======== HELPERS DE PLAN ========

    def _get_user_plan(self, user) -> str:
        settings = getattr(user, "settings", None)
        plan = getattr(settings, "plan", None)
        if plan in {"free", "plus", "pro"}:
            return plan
        return "free"

    def _get_plan_limits(self, plan: str) -> dict:
        # Valores base, luego los podrás mover a settings o base de datos
        config = {
            "free": {"max_monthly_tx": 300},
            "plus": {"max_monthly_tx": 2000},
            "pro": {"max_monthly_tx": None},  # sin límite
        }
        return config.get(plan, config["free"])

    def validate(self, attrs):
        user = self.context["request"].user

        # ----- 1) amount > 0 -----
        amount = attrs.get("amount", getattr(self.instance, "amount", None))
        if amount is None or Decimal(amount) <= 0:
            raise serializers.ValidationError(
                {"amount": "El monto debe ser mayor a 0."}
            )

        # ----- 2) owner-consistency en FKs -----
        for f in [
            "account",
            "category",
            "vendor",
            "income_source",
            "debt",
            "installment",
            "scheduled_payment",
        ]:
            self._assert_owner(attrs.get(f), f)

        # ----- 3) coherencia tipo de transacción -----
        tx_type = attrs.get("type", getattr(self.instance, "type", None))
        account = attrs.get("account", getattr(self.instance, "account", None))
        date = attrs.get("date", getattr(self.instance, "date", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        income_source = attrs.get(
            "income_source", getattr(self.instance, "income_source", None)
        )
        debt = attrs.get("debt", getattr(self.instance, "debt", None))
        installment = attrs.get(
            "installment", getattr(self.instance, "installment", None)
        )
        scheduled_payment = attrs.get(
            "scheduled_payment",
            getattr(self.instance, "scheduled_payment", None),
        )

        # 3.a) coherencia category <-> type (si Category tiene campo 'type')
        if category and hasattr(category, "type"):
            if tx_type == "expense" and category.type != "expense":
                raise serializers.ValidationError(
                    {"category": "La categoría debe ser de gasto."}
                )
            if tx_type == "income" and category.type != "income":
                raise serializers.ValidationError(
                    {"category": "La categoría debe ser de ingreso."}
                )

        # 3.b) income_source solo en ingresos
        if income_source and tx_type != "income":
            raise serializers.ValidationError(
                {
                    "income_source": "Solo puedes asociar una fuente de ingreso "
                    "a transacciones de tipo 'income'."
                }
            )

        # 3.c) debt / installment solo en gastos
        if (debt or installment) and tx_type != "expense":
            raise serializers.ValidationError(
                {
                    "debt": "Las deudas/cuotas solo deben asociarse a transacciones de gasto."
                }
            )

        # 3.d) coherencia debt vs installment
        if installment and not debt:
            if hasattr(installment, "debt") and installment.debt:
                attrs["debt"] = installment.debt
            else:
                raise serializers.ValidationError(
                    {
                        "installment": "La cuota debe estar asociada a una deuda válida."
                    }
                )
        if debt and installment and getattr(installment, "debt_id", None) != debt.id:
            raise serializers.ValidationError(
                {
                    "installment": "La cuota no pertenece a la deuda seleccionada."
                }
            )

        # 3.e) scheduled_payment coherente (opcional, puedes endurecer más)
        if scheduled_payment and getattr(
            scheduled_payment, "status", None
        ) == ScheduledPayment.Status.PAID:
            raise serializers.ValidationError(
                {
                    "scheduled_payment": (
                        "Este pago programado ya está marcado como pagado."
                    )
                }
            )

        # ----- 4) límite mensual por cuenta (si aplica) -----
        if tx_type == "expense" and account and date:
            monthly_limit = getattr(account, "monthly_expense_limit", None)
            lock_on_limit = getattr(account, "lock_on_limit", False)

            if monthly_limit:
                month_total = account_month_expense_total(account, date)
                projected = month_total + Decimal(amount)
                if projected > Decimal(monthly_limit):
                    if lock_on_limit:
                        raise serializers.ValidationError(
                            {
                                "amount": "Límite mensual de gasto para la cuenta excedido."
                            }
                        )
                    # Si no bloquea, se permitirá y una señal/alerta podrá notificar

        # ----- 5) límite de transacciones mensuales por plan -----
        # Solo se aplica en creaciones, no en updates
        if self.instance is None and user and date:
            plan = self._get_user_plan(user)
            limits = self._get_plan_limits(plan)
            max_monthly_tx = limits.get("max_monthly_tx")

            if max_monthly_tx is not None:
                current_count = user_month_tx_count(user, date)
                if current_count >= max_monthly_tx:
                    raise serializers.ValidationError(
                        {
                            "non_field_errors": (
                                "Has alcanzado el máximo de transacciones permitidas "
                                f"en este mes para tu plan ({max_monthly_tx})."
                            )
                        }
                    )

        return attrs

    def create(self, validated_data):
        """
        Manejo de tags por id desde el body:
        "tags": [1, 2, 3]
        """
        tags_data = self.initial_data.get("tags")
        tx = super().create(validated_data)
        if isinstance(tags_data, list):
            tx.tags.set(
                Tag.objects.filter(owner=tx.owner, id__in=tags_data)
            )
        return tx

    def update(self, instance, validated_data):
        tags_data = self.initial_data.get("tags")
        tx = super().update(instance, validated_data)
        if isinstance(tags_data, list):
            tx.tags.set(
                Tag.objects.filter(owner=tx.owner, id__in=tags_data)
            )
        return tx
