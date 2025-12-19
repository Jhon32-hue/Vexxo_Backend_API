from rest_framework import viewsets
from audit.models import AuditLog
from audit.serializers import AuditoriaSerializer


class AuditoriaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all().order_by('-ts')
    serializer_class = AuditoriaSerializer

