from rest_framework import viewsets
from rules.models import Rule
from rules.serializers import ReglaSerializer


class ReglaViewSet(viewsets.ModelViewSet):
    queryset = Rule.objects.all().order_by('priority', 'id')
    serializer_class = ReglaSerializer

