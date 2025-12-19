from rest_framework import viewsets
from vendors.models import Vendor
from vendors.serializers import ProveedorSerializer


class ProveedorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all().order_by('name')
    serializer_class = ProveedorSerializer

