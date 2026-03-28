# transactions/Views/participants_view.py
from decimal import Decimal

from django.db.models import Sum, Count, Q
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from finance.transactions.Models.transacciones import TransactionParticipant
from finance.transactions.Serializers.participant_serializer import (
    TransactionParticipantSerializer,
)
from contacts.models import Contact


class TransactionParticipantViewSet(viewsets.ModelViewSet):
    """
    API para gestionar participantes de transacciones
    (gastos compartidos / reembolsos / favores).

    Casos de uso:
    - Listar participantes de mis transacciones.
    - Filtrar por contacto (?contact_id).
    - Ver resumen por contacto (te debe / debes / liquidado).
    - Marcar participación como liquidada.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TransactionParticipantSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["display_name", "email", "phone"]

    def get_queryset(self):
        return (
            TransactionParticipant.objects.filter(owner=self.request.user)
            .select_related("transaction", "contact")
            .all()
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # ------- LISTADOS ESPECIALES -------

    @action(detail=False, methods=["get"])
    def by_contact(self, request):
        """
        Lista de participaciones filtradas por contacto.
        ?contact_id=<id>
        """
        contact_id = request.query_params.get("contact_id")
        if not contact_id:
            return Response(
                {"detail": "contact_id es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            contact = Contact.objects.get(pk=contact_id, owner=request.user)
        except Contact.DoesNotExist:
            return Response(
                {"detail": "Contacto no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = self.get_queryset().filter(contact=contact)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary_by_contact(self, request):
        """
        Resumen neto por contacto:

        [
          {
            "contact_id": 1,
            "name": "Ana",
            "net_balance": 50.00,  # >0 => te debe, <0 => debes
            "total_active": 3,
            "label": "Te debe"
          },
          ...
        ]
        """
        qs = self.get_queryset().filter(contact__isnull=False, status="active")

        aggregates = (
            qs.values("contact_id", "contact__name")
            .annotate(
                total_creditor=Sum(
                    "share_amount",
                    filter=Q(direction="user_creditor"),
                ),
                total_debtor=Sum(
                    "share_amount",
                    filter=Q(direction="user_debtor"),
                ),
                total_active=Count("id"),
            )
            .order_by("contact__name")
        )

        data = []
        for row in aggregates:
            total_creditor = Decimal(row["total_creditor"] or 0)
            total_debtor = Decimal(row["total_debtor"] or 0)
            net = (total_creditor - total_debtor).quantize(Decimal("0.01"))

            data.append(
                {
                    "contact_id": row["contact_id"],
                    "name": row["contact__name"],
                    "net_balance": net,
                    "total_active": row["total_active"],
                    "label": (
                        "Te debe"
                        if net > 0
                        else "Debes" if net < 0 else "Liquidado"
                    ),
                }
            )

        return Response(data, status=status.HTTP_200_OK)

    # ------- ACCIONES SOBRE UNA PARTICIPACIÓN -------

    @action(detail=True, methods=["post"])
    def mark_settled(self, request, pk=None):
        """
        Marca una participación como liquidada (paid = share, status=settled).
        """
        participant = self.get_object()
        participant.mark_settled()

        serializer = self.get_serializer(participant)
        return Response(serializer.data, status=status.HTTP_200_OK)
