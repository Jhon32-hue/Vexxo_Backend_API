from rest_framework import viewsets
from finance.vendors.models import Vendor
from finance.vendors.serializers import ProveedorSerializer


class ProveedorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all().order_by('name')
    serializer_class = ProveedorSerializer
