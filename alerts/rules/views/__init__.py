from rest_framework import viewsets
from alerts.rules.models import Rule
from alerts.rules.serializers import ReglaSerializer


class ReglaViewSet(viewsets.ModelViewSet):
    queryset = Rule.objects.all().order_by('priority', 'id')
    serializer_class = ReglaSerializer
