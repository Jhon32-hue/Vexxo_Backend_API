from decimal import Decimal

from django.contrib.auth import get_user_model
from identity.users.models import User
from django.utils import timezone
from rest_framework import serializers

from finance.transactions.Models.transacciones import (
    Transaction,
    Tag,
    IncomeSource,
    ScheduledPayment,
    TransactionParticipant,
)
from finance.transactions.utils_limits import account_month_expense_total, user_month_tx_count
from identity.users.domain.plan_matrix import get_plan_capabilities
from identity.users.services.product_access_service import validate_scheduled_payments_limit

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
        activating_pending = (
            self.instance is not None
            and attrs.get("status") == ScheduledPayment.Status.PENDING
            and getattr(self.instance, "status", None) != ScheduledPayment.Status.PENDING
        )
        if self.instance is None or activating_pending:
            validate_scheduled_payments_limit(
                self.context["request"].user,
                source="transactions.scheduled_payments.create" if self.instance is None else "transactions.scheduled_payments.reactivate",
            )
        for f in ["account", "category", "vendor", "debt", "installment"]:
            self._assert_owner(attrs.get(f), f)
        return attrs


# ====== PARTICIPANTES ======

class TransactionParticipantSerializer(BaseOwnerSerializer):
    pending_amount = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TransactionParticipant
        fields = [
            "id",
            "transaction",
            "display_name",
            "email",
            "phone",
            "role",
            "status",
            "invite_status",
            "share_amount",
            "paid_amount",
            "pending_amount",
            "linked_user",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("owner", "created_at", "updated_at", "pending_amount")

    def get_pending_amount(self, obj):
        return obj.pending_amount

    def validate(self, attrs):
        self._assert_owner(attrs.get("transaction"), "transaction")
        return attrs


# ====== TRANSACTION ======

class TransactionSerializer(BaseOwnerSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)

    # Solo lectura en la respuesta; escritura vía create/update con initial_data
    participants = TransactionParticipantSerializer(many=True, read_only=True)

    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = (
            "owner",
            "created_at",
            "updated_at",
            "fingerprint",
            "reimbursed",
            "reimbursement_transaction",
        )

    # ======== PLAN HELPERS ========

    # ======== VALIDACIÓN PRINCIPAL ========

    def validate(self, attrs):
        user = self.context["request"].user
        instance = self.instance

        # 1) monto
        amount = attrs.get("amount", getattr(instance, "amount", None))
        if amount is None or Decimal(amount) <= 0:
            raise serializers.ValidationError(
                {"amount": "El monto debe ser mayor a 0."}
            )

        # 2) owner-consistency en FKs
        for f in [
            "account",
            "category",
            "vendor",
            "income_source",
            "debt",
            "installment",
            "scheduled_payment",
            "payment_intent",
        ]:
            self._assert_owner(attrs.get(f) or getattr(instance, f, None), f)

        tx_type = attrs.get("type", getattr(instance, "type", None))
        account = attrs.get("account", getattr(instance, "account", None))
        date = attrs.get("date", getattr(instance, "date", None))
        category = attrs.get("category", getattr(instance, "category", None))
        income_source = attrs.get(
            "income_source", getattr(instance, "income_source", None)
        )
        debt = attrs.get("debt", getattr(instance, "debt", None))
        installment = attrs.get(
            "installment", getattr(instance, "installment", None)
        )
        scheduled_payment = attrs.get(
            "scheduled_payment",
            getattr(instance, "scheduled_payment", None),
        )

        # 3.a) categoría coherente
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

        # 3.c) deudas/cuotas solo en gastos
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

        # 3.e) scheduled_payment coherente
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

        # 3.f) reembolsables: solo gastos
        is_reimbursable = attrs.get(
            "is_reimbursable",
            getattr(instance, "is_reimbursable", False),
        )
        if is_reimbursable and tx_type != "expense":
            raise serializers.ValidationError(
                {"is_reimbursable": "Solo los gastos pueden ser reembolsables."}
            )

        # 4) límite mensual por cuenta
        if tx_type == "expense" and account and date:
            monthly_limit = getattr(account, "monthly_expense_limit", None)
            lock_on_limit = getattr(account, "lock_on_limit", False)

            if monthly_limit:
                month_total = account_month_expense_total(account, date)
                projected = month_total + Decimal(amount)
                if projected > Decimal(monthly_limit) and lock_on_limit:
                    raise serializers.ValidationError(
                        {
                            "amount": "Límite mensual de gasto para la cuenta excedido."
                        }
                    )

        # 5) límite por plan (solo en creación)
        if instance is None and user and date:
            max_monthly_tx = get_plan_capabilities(getattr(user, "plan", "free")).get(
                "max_monthly_tx_per_account"
            )

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

        # 6) splits: si es hija, no anidamos más de un nivel
        parent = attrs.get("parent", getattr(instance, "parent", None))
        if parent and parent.parent_id:
            raise serializers.ValidationError(
                {"parent": "No puedes anidar splits a más de un nivel."}
            )

        return attrs

    # ======== CREATE/UPDATE ========

    def create(self, validated_data):
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

    # ======== HELPER PARA COMENTARIOS ========

    @staticmethod
    def add_comment(tx: Transaction, text: str, user: User):
        comments = list(tx.comments or [])
        comments.append(
            {
                "author_id": user.id,
                "text": text,
                "created_at": timezone.now().isoformat(),
            }
        )
        tx.comments = comments
        tx.save(update_fields=["comments"])
        return tx
