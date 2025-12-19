from rest_framework import serializers
from accounts.models import Account
from decimal import Decimal


class AccountSerializer(serializers.ModelSerializer):
    current_balance = serializers.SerializerMethodField(read_only=True)
    total_transactions = serializers.SerializerMethodField(read_only=True)
    is_closed = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Account
        fields = [
            "id",
            "owner",
            "name",
            "type",
            "currency",
            "initial_balance",
            "balance",
            "current_balance",
            "total_transactions",
            "is_active",
            "is_closed",
            "created_at",
            "updated_at",
            "closed_at",
        ]
        read_only_fields = ["balance", "current_balance", "total_transactions", "created_at", "updated_at", "closed_at"]

    def get_current_balance(self, obj):
        return obj.current_balance()

    def get_total_transactions(self, obj):
        return obj.transactions_qs().count()

    def get_is_closed(self, obj):
        return not obj.is_active and obj.closed_at is not None

    def validate_name(self, value):
        user = self.context["request"].user
        if Account.objects.filter(owner=user, name=value).exists():
            raise serializers.ValidationError("Ya existe una cuenta con este nombre.")
        return value

    def validate(self, data):
        if data.get("initial_balance", Decimal("0")) < 0:
            raise serializers.ValidationError({"initial_balance": "El saldo inicial no puede ser negativo."})
        return data
