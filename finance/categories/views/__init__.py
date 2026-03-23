from rest_framework import viewsets
from finance.categories.models import Category
from finance.categories.serializers import CategoriaSerializer


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategoriaSerializer
