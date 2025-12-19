from rest_framework import serializers
from invoices.models import Invoice, InvoiceLine


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = '__all__'


class FacturaSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'

