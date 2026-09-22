from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from documents.links_to_transactions.models import DocumentTransactionLink
from documents.links_to_transactions.serializers import DocumentTransactionLinkSerializer


class DocumentTransactionLinkViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = DocumentTransactionLinkSerializer

    def get_queryset(self):
        return DocumentTransactionLink.objects.filter(owner=self.request.user).select_related("document", "transaction")
