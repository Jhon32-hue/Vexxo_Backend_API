from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.utils.timezone import make_aware
from datetime import datetime

from audit.models.audit import AuditLog
from audit.serializers.audit_serializers import AuditoriaSerializer


class AuditoriaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Auditoría central explicable de MindWallet.
    """

    serializer_class = AuditoriaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params

        queryset = AuditLog.objects.filter(user=user)

        if module := params.get("module"):
            queryset = queryset.filter(module=module)

        if action := params.get("action"):
            queryset = queryset.filter(action=action)

        if source := params.get("source"):
            queryset = queryset.filter(source=source)

        if impact := params.get("impact"):
            queryset = queryset.filter(impact=impact)

        if entity := params.get("entity"):
            queryset = queryset.filter(entity=entity)

        if entity_id := params.get("entity_id"):
            queryset = queryset.filter(entity_id=entity_id)

        if date_from := params.get("date_from"):
            queryset = queryset.filter(ts__gte=self._parse_date(date_from))

        if date_to := params.get("date_to"):
            queryset = queryset.filter(ts__lte=self._parse_date(date_to))

        return queryset.order_by("-ts")

    def _parse_date(self, value):
        try:
            return make_aware(datetime.fromisoformat(value))
        except Exception:
            return None
