from rest_framework import viewsets
from goals.models import Goal
from goals.serializers import MetaSerializer


class MetaViewSet(viewsets.ModelViewSet):
    queryset = Goal.objects.all().order_by('-target_date')
    serializer_class = MetaSerializer

