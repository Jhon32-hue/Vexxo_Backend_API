import hashlib

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from admin_tools.user_lookup.serializers import (
    SupportUserOverviewSerializer,
    SupportUserSummarySerializer,
)
from admin_tools.user_lookup.services import build_user_support_overview, serialize_user_summary
from identity.users.views.permissions import IsAdminUser
from support.audit.helpers import audit_log
from support.audit.models import AuditLog


User = get_user_model()
MAX_QUERY_LENGTH = 255
MAX_REASON_LENGTH = 500
MAX_CASE_LENGTH = 100


class UserLookupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all().order_by("-created_at")
    permission_classes = [IsAdminUser]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method == "OPTIONS":
            return
        reason = request.headers.get("X-Support-Reason", "").strip()
        if not 10 <= len(reason) <= MAX_REASON_LENGTH:
            raise ValidationError(
                {
                    "support_reason": (
                        f"X-Support-Reason debe tener entre 10 y {MAX_REASON_LENGTH} caracteres."
                    )
                }
            )
        support_case = request.headers.get("X-Support-Case", "").strip()
        if len(support_case) > MAX_CASE_LENGTH:
            raise ValidationError(
                {"support_case": f"X-Support-Case admite maximo {MAX_CASE_LENGTH} caracteres."}
            )
        request.support_reason = reason
        request.support_case = support_case

    def get_serializer_class(self):
        if self.action == "retrieve":
            return SupportUserOverviewSerializer
        return SupportUserSummarySerializer

    def list(self, request, *args, **kwargs):
        query = request.query_params.get("q", "").strip()
        if not 3 <= len(query) <= MAX_QUERY_LENGTH:
            return Response(
                {"q": f"La busqueda requiere entre 3 y {MAX_QUERY_LENGTH} caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        users = list(
            self.get_queryset()
            .filter(
                Q(email__icontains=query)
                | Q(username__icontains=query)
                | Q(phone_number__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
            )[:20]
        )
        payload = [serialize_user_summary(user) for user in users]
        audit_log(
            user=request.user,
            module="admin_tools.user_lookup",
            action=AuditLog.Action.READ,
            source=AuditLog.Source.USER,
            impact=AuditLog.Impact.MEDIUM,
            entity="UserSearch",
            entity_id=request.user.id,
            description="Busqueda interna de usuarios.",
            metadata={
                "actor_user_id": request.user.id,
                "support_reason": request.support_reason,
                "support_case": request.support_case,
                "query_hash": hashlib.sha256(query.casefold().encode("utf-8")).hexdigest(),
                "result_count": len(payload),
            },
        )
        return Response(
            {"count": len(payload), "results": self.get_serializer(payload, many=True).data}
        )

    def retrieve(self, request, *args, **kwargs):
        target = self.get_object()
        payload = build_user_support_overview(target)
        audit_log(
            user=target,
            module="admin_tools.user_lookup",
            action=AuditLog.Action.READ,
            source=AuditLog.Source.USER,
            impact=AuditLog.Impact.MEDIUM,
            entity="User",
            entity_id=target.id,
            description="Consulta interna de vista 360 de usuario.",
            metadata={
                "actor_user_id": request.user.id,
                "support_reason": request.support_reason,
                "support_case": request.support_case,
            },
        )
        return Response(self.get_serializer(payload).data)
