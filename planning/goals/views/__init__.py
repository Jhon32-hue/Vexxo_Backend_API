from rest_framework import viewsets
from planning.goals.models import Goal
from planning.goals.serializers import MetaSerializer


class MetaViewSet(viewsets.ModelViewSet):
    queryset = Goal.objects.all().order_by('-target_date')
    serializer_class = MetaSerializer
