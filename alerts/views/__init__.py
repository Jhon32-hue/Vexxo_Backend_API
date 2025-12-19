from rest_framework import viewsets
from alerts.models import Alert
from alerts.serializers import AlertaSerializer


class AlertaViewSet(viewsets.ModelViewSet):
    queryset = Alert.objects.all().order_by('-created_at')
    serializer_class = AlertaSerializer

