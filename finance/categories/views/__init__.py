from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from finance.categories.models import Category
from finance.categories.serializers import CategoriaSerializer


class CategoriaViewSet(viewsets.ModelViewSet):
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Category.objects.filter(owner=self.request.user).order_by("name")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
