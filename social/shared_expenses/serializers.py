from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import serializers

from contacts.models import Contact
from finance.transactions.Models import Transaction
from finance.transactions.Serializers.transactions_serializers import TransactionSerializer
from social.shared_expenses.models import SharedExpense, SharedExpenseSettlement, SharedExpenseShare
from social.shared_expenses.services import canonical_request_hash, create_shared_expense
from social.teams.models import Team

User = get_user_model()


def validate_unique_share_identities(shares):
    identities = []
    for index, share in enumerate(shares):
        if share.get("is_payer"):
            key = "payer"
        elif share.get("participant_user"):
            key = f"user:{share['participant_user'].pk}"
        elif share.get("contact"):
            key = f"contact:{share['contact'].pk}"
        elif share.get("email"):
            key = f"email:{share['email'].lower()}"
        else:
            key = f"external:{share.get('display_name', '').strip().lower()}:{index}"
        identities.append(key)
    if len(identities) != len(set(identities)):
        raise serializers.ValidationError({"shares": "No se puede repetir un participante."})
    return shares


class SharedExpenseShareInputSerializer(serializers.Serializer):
    participant_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    contact = serializers.PrimaryKeyRelatedField(queryset=Contact.objects.all(), required=False, allow_null=True)
    is_payer = serializers.BooleanField(default=False)
    display_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, required=False)
    percentage = serializers.DecimalField(max_digits=7, decimal_places=4, required=False)
    weight = serializers.DecimalField(max_digits=12, decimal_places=4, required=False)


class SharedExpenseShareSerializer(serializers.ModelSerializer):
    pending_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    participant_name = serializers.CharField(source="participant_user.display_name", read_only=True)
    contact_name = serializers.CharField(source="contact.name", read_only=True)
    can_accept = serializers.SerializerMethodField()

    class Meta:
        model = SharedExpenseShare
        fields = [
            "public_id",
            "participant_user",
            "participant_name",
            "contact",
            "contact_name",
            "is_payer",
            "display_name",
            "email",
            "expected_amount",
            "paid_amount",
            "pending_amount",
            "percentage",
            "weight",
            "status",
            "can_accept",
            "accepted_at",
            "disputed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_can_accept(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated or obj.status != SharedExpenseShare.Status.PENDING:
            return False
        email = str(request.user.email or "").strip().lower()
        return obj.participant_user_id == request.user.pk or bool(obj.email and obj.email.lower() == email)


class SharedExpenseSettlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = SharedExpenseSettlement
        fields = ["public_id", "share", "transaction", "recorded_by", "amount", "status", "created_at", "reversed_at"]
        read_only_fields = fields


class SharedExpenseSerializer(serializers.ModelSerializer):
    shares = SharedExpenseShareSerializer(many=True, read_only=True)
    settlements = SharedExpenseSettlementSerializer(many=True, read_only=True)
    transaction_description = serializers.CharField(source="transaction.description", read_only=True)
    owner_name = serializers.CharField(source="owner.display_name", read_only=True)

    class Meta:
        model = SharedExpense
        fields = [
            "public_id",
            "owner",
            "owner_name",
            "transaction",
            "transaction_description",
            "team",
            "split_method",
            "status",
            "total_amount",
            "currency",
            "version",
            "shares",
            "settlements",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SharedExpenseCreateSerializer(serializers.Serializer):
    transaction = serializers.PrimaryKeyRelatedField(queryset=Transaction.objects.all(), required=False)
    transaction_payload = serializers.JSONField(required=False)
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all(), required=False, allow_null=True)
    split_method = serializers.ChoiceField(choices=SharedExpense.SplitMethod.choices)
    shares = SharedExpenseShareInputSerializer(many=True, min_length=2)

    def validate(self, attrs):
        transaction = attrs.get("transaction")
        payload = attrs.get("transaction_payload")
        if bool(transaction) == bool(payload):
            raise serializers.ValidationError("Indica transaction o transaction_payload, pero no ambos.")
        if payload:
            tx_serializer = TransactionSerializer(data=payload, context=self.context)
            tx_serializer.is_valid(raise_exception=True)
            if tx_serializer.validated_data.get("type") != Transaction.Type.EXPENSE:
                raise serializers.ValidationError({"transaction_payload": "Solo se puede dividir un gasto."})
            self._transaction_validated_data = tx_serializer.validated_data
            self._tags_data = payload.get("tags")
        validate_unique_share_identities(attrs["shares"])
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        transaction = validated_data.get("transaction")
        expense, _created = create_shared_expense(
            actor=request.user,
            split_method=validated_data["split_method"],
            share_specs=validated_data["shares"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            request_hash=canonical_request_hash(self.initial_data),
            request_id=getattr(request, "vexxo_request_id", ""),
            team=validated_data.get("team"),
            source_transaction=transaction,
            transaction_validated_data=getattr(self, "_transaction_validated_data", None),
            tags_data=getattr(self, "_tags_data", None),
        )
        return expense


class SharedExpenseActionSerializer(serializers.Serializer):
    share_id = serializers.UUIDField()
    base_version = serializers.IntegerField(min_value=1)


class SharedExpenseVersionSerializer(serializers.Serializer):
    base_version = serializers.IntegerField(min_value=1)


class SharedExpenseRevisionSerializer(serializers.Serializer):
    split_method = serializers.ChoiceField(choices=SharedExpense.SplitMethod.choices)
    shares = SharedExpenseShareInputSerializer(many=True, min_length=2)
    base_version = serializers.IntegerField(min_value=1)

    def validate_shares(self, value):
        return validate_unique_share_identities(value)


class SharedExpenseSettlementInputSerializer(SharedExpenseActionSerializer):
    share_id = serializers.UUIDField()
    transaction = serializers.PrimaryKeyRelatedField(queryset=Transaction.objects.all())
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal("0.01"))
