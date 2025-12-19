from rest_framework import viewsets, parsers
from invoices.models import Invoice, InvoiceLine
from invoices.serializers import FacturaSerializer, InvoiceLineSerializer


class FacturaViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all().order_by('-created_at')
    serializer_class = FacturaSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]


class FacturaLineaViewSet(viewsets.ModelViewSet):
    queryset = InvoiceLine.objects.select_related('invoice').all()
    serializer_class = InvoiceLineSerializer
