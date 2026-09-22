from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.open_banking.models import OpenBankingConnection
from integrations.open_banking.serializers import OpenBankingTimelineEventSerializer
from support.access_history.models import SupportAccessRecord


class OpenBankingSupportTimelineView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, public_id):
        reason = str(request.headers.get("X-Support-Reason") or "").strip()
        case_reference = str(request.headers.get("X-Support-Case") or "").strip()
        if len(reason) < 10 or len(reason) > 500:
            return Response(
                {"detail": "X-Support-Reason debe tener entre 10 y 500 caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(case_reference) < 3 or len(case_reference) > 120:
            return Response(
                {"detail": "X-Support-Case es obligatorio y debe tener entre 3 y 120 caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        connection = (
            OpenBankingConnection.objects.select_related("owner", "consent", "institution")
            .prefetch_related("account_links", "timeline_events", "reconciliation_issues")
            .filter(public_id=public_id)
            .first()
        )
        if connection is None:
            return Response({"detail": "Conexion no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        SupportAccessRecord.objects.create(
            staff_user=request.user,
            subject_user=connection.owner,
            module="open_banking",
            action="read",
            target_type="OpenBankingConnection",
            target_id=str(connection.public_id),
            reason=reason,
            case_reference=case_reference,
            request_id=str(getattr(request, "request_id", "") or "")[:64],
            safe_metadata={"provider": connection.provider},
        )
        events = connection.timeline_events.order_by("occurred_at", "pk")[:1000]
        return Response(
            {
                "connection": {
                    "public_id": str(connection.public_id),
                    "owner_id": str(connection.owner_id),
                    "provider": connection.provider,
                    "institution": connection.institution.name if connection.institution else connection.institution_name,
                    "institution_code": connection.institution.code if connection.institution else "",
                    "status": connection.status,
                    "consent_status": connection.consent.status,
                    "consent_expires_at": connection.consent.expires_at,
                    "last_synced_at": connection.last_synced_at,
                    "next_sync_at": connection.next_sync_at,
                    "sync_cursor_present": connection.account_links.exclude(sync_cursor="").exists(),
                    "linked_accounts": connection.account_links.filter(is_active=True).count(),
                    "open_reconciliation_issues": connection.reconciliation_issues.filter(status="open").count(),
                    "error_code": connection.error_code,
                },
                "timeline": OpenBankingTimelineEventSerializer(events, many=True).data,
            }
        )
