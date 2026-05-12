from django.utils import timezone
from django.db import models
from rest_framework import serializers

from finance.budgets.models import SharedBudget
from finance.transactions.Models.transacciones import (
    IncomeSource,
    Tag,
    Transaction,
    TransactionParticipant,
)
from finance.transactions.Models.intake import TransactionExternalDetails
from finance.transactions.transaction_validation_service import (
    apply_tag_selection,
    assert_ledger_owner,
    assert_owner,
    resolve_transaction_ledger_owner,
    validate_transaction_payload,
)
from finance.transactions.transaction_write_service import create_manual_transaction, update_manual_transaction


class BaseOwnerSerializer(serializers.ModelSerializer):
    def _assert_owner(self, obj, field):
        user = self.context["request"].user
        assert_owner(user, obj, field)

    def create(self, validated_data):
        validated_data.setdefault("owner", self.context["request"].user)
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


class TransactionParticipantSerializer(BaseOwnerSerializer):
    contact_name = serializers.CharField(source="contact.name", read_only=True)
    contact_nickname = serializers.CharField(source="contact.nickname", read_only=True)
    pending_amount = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TransactionParticipant
        fields = [
            "id",
            "transaction",
            "contact",
            "contact_name",
            "contact_nickname",
            "display_name",
            "email",
            "phone",
            "direction",
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
        tx = attrs.get("transaction") or getattr(self.instance, "transaction", None)
        if tx:
            resolve_transaction_ledger_owner(
                user=self.context["request"].user,
                account=getattr(tx, "account", None),
                instance=tx,
            )
        ledger_owner = getattr(tx, "owner", self.context["request"].user)
        assert_ledger_owner(ledger_owner, tx, "transaction")
        assert_ledger_owner(ledger_owner, attrs.get("contact") or getattr(self.instance, "contact", None), "contact")
        contact = attrs.get("contact") or getattr(self.instance, "contact", None)
        share_amount = attrs.get("share_amount", getattr(self.instance, "share_amount", None))
        paid_amount = attrs.get("paid_amount", getattr(self.instance, "paid_amount", None))

        if share_amount is None or share_amount <= 0:
            raise serializers.ValidationError({"share_amount": "El monto de la participación debe ser mayor a 0."})

        if paid_amount is not None:
            if paid_amount < 0:
                raise serializers.ValidationError({"paid_amount": "El monto pagado no puede ser negativo."})
            if paid_amount > share_amount:
                raise serializers.ValidationError({"paid_amount": "El monto pagado no puede ser mayor al share asignado."})

        if tx:
            qs = TransactionParticipant.objects.filter(transaction=tx)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            total_existing = qs.aggregate(total=models.Sum("share_amount"))["total"] or 0
            projected = total_existing + share_amount
            if projected > tx.amount:
                raise serializers.ValidationError(
                    {"share_amount": "La suma de las participaciones excede el monto de la transacción."}
                )

        if contact and not (attrs.get("display_name") or getattr(self.instance, "display_name", "")):
            effective_name = getattr(contact, "effective_name", None)
            attrs["display_name"] = effective_name() if callable(effective_name) else (contact.nickname or contact.name)
        return attrs

    def create(self, validated_data):
        tx = validated_data.get("transaction")
        if tx is not None:
            validated_data["owner"] = tx.owner
        participant = super().create(validated_data)
        participant._event_actor_id = getattr(self.context.get("request"), "user", None).id if self.context.get("request") else ""
        return participant


class TransactionExternalDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionExternalDetails
        exclude = ("transaction",)


class TransactionSerializer(BaseOwnerSerializer):
    budget_context_shared_budget = serializers.PrimaryKeyRelatedField(
        queryset=SharedBudget.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )
    account_name = serializers.CharField(source="account.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    participants = TransactionParticipantSerializer(many=True, read_only=True)
    external_details = TransactionExternalDetailsSerializer(read_only=True)

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
            "budget_attribution_source",
            "payment_schedule_run",
        )

    def validate(self, attrs):
        return validate_transaction_payload(
            user=self.context["request"].user,
            attrs=attrs,
            instance=self.instance,
            budget_context_shared_budget=attrs.get("budget_context_shared_budget"),
        )

    def create(self, validated_data):
        actor = getattr(self.context.get("request"), "user", None)
        budget_context_shared_budget = validated_data.pop("budget_context_shared_budget", None)
        return create_manual_transaction(
            validated_data=validated_data,
            actor=actor,
            tags_data=self.initial_data.get("tags"),
            budget_context_shared_budget=budget_context_shared_budget,
        )

    def update(self, instance, validated_data):
        actor = getattr(self.context.get("request"), "user", None)
        budget_context_shared_budget = validated_data.pop("budget_context_shared_budget", None)
        return update_manual_transaction(
            instance=instance,
            validated_data=validated_data,
            actor=actor,
            tags_data=self.initial_data.get("tags"),
            budget_context_shared_budget=budget_context_shared_budget,
        )

    @staticmethod
    def add_comment(tx: Transaction, text: str, user):
        comments = list(tx.comments or [])
        comments.append(
            {
                "author_id": user.id,
                "text": text,
                "created_at": timezone.now().isoformat(),
            }
        )
        tx.comments = comments
        tx.save(update_fields=["comments", "updated_at"])
        return tx
