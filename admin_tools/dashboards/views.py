from rest_framework.response import Response
from rest_framework.views import APIView

from admin_tools.dashboards.services import build_operations_snapshot
from identity.users.views.permissions import IsAdminUser
from support.audit.helpers import audit_log
from support.audit.models import AuditLog


class OperationsDashboardView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        payload = build_operations_snapshot()
        audit_log(
            user=request.user,
            module="admin_tools.dashboards",
            action=AuditLog.Action.READ,
            source=AuditLog.Source.USER,
            impact=AuditLog.Impact.LOW,
            entity="OperationsDashboard",
            entity_id="current",
            description="Consulta del dashboard operativo central.",
            metadata={"request_id": getattr(request, "request_id", "")},
        )
        return Response(payload)
