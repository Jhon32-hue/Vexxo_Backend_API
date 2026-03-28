from rest_framework import serializers
from contacts.models.contact import Contact


class ContactSerializer(serializers.ModelSerializer):
    net_status = serializers.SerializerMethodField()

    class Meta:
        model = Contact
        fields = "__all__"
        read_only_fields = (
            "owner",
            "net_balance",
            "last_activity_at",
            "last_transaction_at",
            "last_transaction_amount",
            "created_at",
            "updated_at",
        )

    def get_net_status(self, obj):
        if obj.net_balance > 0:
            return "they_owe_me"
        if obj.net_balance < 0:
            return "i_owe_them"
        return "settled"

    def validate(self, attrs):
        user = self.context["request"].user
        # Si no viene moneda, usamos la preferida del usuario
        if not attrs.get("currency"):
            attrs["currency"] = getattr(user, "preferred_currency", "COP")
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request:
            validated_data["owner"] = request.user
        return super().create(validated_data)
