# transactions/Serializers/participant_serializer.py

from decimal import Decimal

from django.db import models
from django.contrib.auth import get_user_model
from rest_framework import serializers

from finance.transactions.Models.transacciones import TransactionParticipant

User = get_user_model()


class TransactionParticipantSerializer(serializers.ModelSerializer):
    """
    Gestiona participantes de una transacción (gastos compartidos / reembolsos).
    Incluye:
    - validación de pertenencia (transaction/contact del mismo owner),
    - control de montos (share y paid),
    - control de que la suma de shares no supere el monto de la tx,
    - pending_amount calculado.
    """

    contact_name = serializers.CharField(source="contact.name", read_only=True)
    contact_nickname = serializers.CharField(
        source="contact.nickname", read_only=True
    )
    pending_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True
    )

    class Meta:
        model = TransactionParticipant
        fields = [
            "id",
            "owner",
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
        read_only_fields = ("owner", "created_at", "updated_at", "linked_user")

    # --------- HELPERS ---------

    def _get_user(self):
        req = self.context.get("request")
        return getattr(req, "user", None)

    # --------- VALIDACIÓN GLOBAL ---------

    def validate(self, attrs):
        user = self._get_user()
        instance = getattr(self, "instance", None)

        tx = attrs.get("transaction") or getattr(instance, "transaction", None)
        contact = attrs.get("contact") or getattr(instance, "contact", None)
        share_amount = attrs.get("share_amount", getattr(instance, "share_amount", None))
        paid_amount = attrs.get("paid_amount", getattr(instance, "paid_amount", None))

        # 1) Pertenencia
        if user and tx and tx.owner_id != user.id:
            raise serializers.ValidationError(
                {"transaction": "La transacción no pertenece al usuario autenticado."}
            )

        if user and contact and contact.owner_id != user.id:
            raise serializers.ValidationError(
                {"contact": "El contacto no pertenece al usuario autenticado."}
            )

        # 2) Montos mínimos
        if share_amount is None or Decimal(share_amount) <= 0:
            raise serializers.ValidationError(
                {"share_amount": "El monto de la participación debe ser mayor a 0."}
            )

        if paid_amount is not None:
            if Decimal(paid_amount) < 0:
                raise serializers.ValidationError(
                    {"paid_amount": "El monto pagado no puede ser negativo."}
                )
            if Decimal(paid_amount) > Decimal(share_amount):
                raise serializers.ValidationError(
                    {
                        "paid_amount": (
                            "El monto pagado no puede ser mayor al monto "
                            "asignado a esta participación."
                        )
                    }
                )

        # 3) Sumatoria de shares no puede superar el monto de la transacción
        if tx:
            qs = TransactionParticipant.objects.filter(transaction=tx)
            if instance:
                qs = qs.exclude(pk=instance.pk)

            total_existing = qs.aggregate(total=models.Sum("share_amount"))["total"] or 0
            proyectado = Decimal(total_existing) + Decimal(share_amount)
            if proyectado > tx.amount:
                raise serializers.ValidationError(
                    {
                        "share_amount": (
                            "La suma de las participaciones excede el monto "
                            "de la transacción."
                        )
                    }
                )

        return attrs

    # --------- CREATE / UPDATE ---------

    def create(self, validated_data):
        user = self._get_user()
        if user:
            validated_data["owner"] = user

        participant = super().create(validated_data)

        # Congelamos display_name si no viene
        if not participant.display_name and participant.contact:
            display = getattr(participant.contact, "effective_name", None)
            if callable(display):
                display = display()
            if not display:
                display = participant.contact.name
            participant.display_name = display
            participant.save(update_fields=["display_name"])

        return participant

    def update(self, instance, validated_data):
        participant = super().update(instance, validated_data)

        if not participant.display_name and participant.contact:
            display = getattr(participant.contact, "effective_name", None)
            if callable(display):
                display = display()
            if not display:
                display = participant.contact.name
            participant.display_name = display
            participant.save(update_fields=["display_name"])

        return participant
