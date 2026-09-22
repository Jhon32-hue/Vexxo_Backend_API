from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.monthly_reports.models import MonthlyReportClose
from reports.monthly_reports.services import close_monthly_report


def _serialize(close: MonthlyReportClose) -> dict:
    return {
        "id": close.pk,
        "period_start": close.period_start,
        "period_end": close.period_end,
        "currency": close.currency,
        "timezone": close.timezone_name,
        "version": close.version,
        "status": close.status,
        "is_current": close.is_current,
        "snapshot_id": close.snapshot_id,
        "supersedes_id": close.supersedes_id,
        "regeneration_reason": close.regeneration_reason,
        "closed_at": close.closed_at,
    }


class MonthlyReportCloseListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = MonthlyReportClose.objects.filter(owner=request.user).select_related("snapshot")[:120]
        return Response([_serialize(row) for row in rows])

    def post(self, request):
        regenerate = request.data.get("regenerate", False) is True
        close, created = close_monthly_report(
            owner=request.user,
            month=str(request.data.get("month") or ""),
            currency=str(request.data.get("currency") or getattr(request.user, "preferred_currency", "COP")),
            timezone_name=str(request.data.get("timezone") or getattr(request.user, "timezone_name", "America/Bogota")),
            regenerate=regenerate,
            reason=str(request.data.get("reason") or ""),
        )
        return Response(_serialize(close), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
