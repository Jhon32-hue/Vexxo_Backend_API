from rest_framework import viewsets, permissions, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from contacts.models import Contact
from contacts.serializers import ContactSerializer


class ContactViewSet(viewsets.ModelViewSet):
    """
    Gestión de contactos financieros (roomies, clientes, pareja, etc.)
    Integrado con el plan del usuario mediante user.can_add_contact().
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ContactSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "nickname", "email", "phone"]

    def get_queryset(self):
        user = self.request.user
        qs = Contact.objects.filter(owner=user)

        relationship = self.request.query_params.get("relationship")
        archived = self.request.query_params.get("archived")
        status_param = self.request.query_params.get("status")

        if relationship:
            qs = qs.filter(relationship=relationship)

        if archived is not None:
            qs = qs.filter(is_archived=(archived.lower() == "true"))

        # Estado financiero: deudor/acreedor/liquidado
        if status_param == "debtor":
            qs = qs.filter(net_balance__lt=0)
        elif status_param == "creditor":
            qs = qs.filter(net_balance__gt=0)
        elif status_param == "settled":
            qs = qs.filter(net_balance=0)

        return qs.order_by("name")

    def perform_create(self, serializer):
        user = self.request.user
        # límite de contactos por plan
        if hasattr(user, "can_add_contact") and not user.can_add_contact():
            raise ValidationError(
                {
                    "non_field_errors": (
                        "Has alcanzado el límite de contactos permitidos "
                        "para tu plan actual."
                    )
                }
            )
        serializer.save(owner=user)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        contact = self.get_object()
        contact.is_archived = True
        contact.save(update_fields=["is_archived"])
        return Response({"detail": "Contacto archivado."})

    @action(detail=True, methods=["post"])
    def unarchive(self, request, pk=None):
        contact = self.get_object()
        contact.is_archived = False
        contact.save(update_fields=["is_archived"])
        return Response({"detail": "Contacto restaurado."})
