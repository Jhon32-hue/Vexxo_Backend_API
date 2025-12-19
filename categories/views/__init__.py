from rest_framework import viewsets
from categories.models import Category
from categories.serializers import CategoriaSerializer


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategoriaSerializer

