from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from finance.vendors.models import Vendor
from finance.vendors.serializers import ProveedorSerializer


class ProveedorViewSet(viewsets.ModelViewSet):
    serializer_class = ProveedorSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Vendor.objects.filter(owner=self.request.user).order_by("name")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
