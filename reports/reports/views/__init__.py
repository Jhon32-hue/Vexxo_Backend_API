from datetime import date
from io import BytesIO
from django.http import FileResponse
from django.db.models import Sum
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from finance.budgets.services import build_budget_monthly_overview
from finance.transactions.Models import Transaction
from reports.exports.models import ReportExport
from reports.reports.services import consume_report_export, create_report_snapshot, queue_report_export
from reports.snapshots.models import ReportSnapshot


class CashflowView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start = request.query_params.get('desde')
        end = request.query_params.get('hasta')
        qs = Transaction.objects.filter(owner=request.user, status__in=[Transaction.Status.POSTED, Transaction.Status.RECONCILED])
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        total_ingresos = qs.filter(type='income').aggregate(v=Sum('amount'))['v'] or 0
        total_gastos = qs.filter(type='expense').aggregate(v=Sum('amount'))['v'] or 0
        return Response({
            'ingresos': str(total_ingresos),
            'gastos': str(total_gastos),
            'neto': str((total_ingresos or 0) - (total_gastos or 0)),
        })


class GastosPorCategoriaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = request.query_params.get('periodo', 'mes')
        qs = Transaction.objects.filter(owner=request.user, type='expense', status__in=[Transaction.Status.POSTED, Transaction.Status.RECONCILED])
        data = (
            qs.values('category__name')
            .annotate(total=Sum('amount'))
            .order_by('-total')
        )
        return Response([{ 'categoria': r['category__name'], 'total': str(r['total']) } for r in data])


class BudgetMonthlySummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        month = str(request.query_params.get("month") or "").strip()
        if not month:
            return Response({"detail": "Debes enviar month=YYYY-MM."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(build_budget_monthly_overview(owner=request.user, month=month))


class ReportSnapshotListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = ReportSnapshot.objects.filter(owner=request.user).values("id", "report_type", "period_start", "period_end", "currency", "timezone_name", "as_of", "schema_version", "payload_sha256", "created_at")
        return Response(list(rows))

    def post(self, request):
        try:
            period_start = date.fromisoformat(str(request.data.get("period_start") or ""))
            period_end = date.fromisoformat(str(request.data.get("period_end") or ""))
        except ValueError:
            return Response({"detail": "period_start y period_end deben usar YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        if period_end < period_start:
            return Response({"detail": "El periodo es invalido."}, status=status.HTTP_400_BAD_REQUEST)
        snapshot, created = create_report_snapshot(
            owner=request.user,
            report_type=str(request.data.get("report_type") or "cashflow"),
            period_start=period_start,
            period_end=period_end,
            currency=str(request.data.get("currency") or getattr(request.user, "preferred_currency", "COP"))[:3].upper(),
            timezone_name=str(request.data.get("timezone") or getattr(request.user, "timezone_name", "America/Bogota"))[:64],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response({"id": snapshot.pk, "report_type": snapshot.report_type, "payload": snapshot.payload, "sha256": snapshot.payload_sha256, "as_of": snapshot.as_of}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ReportExportCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        snapshot = ReportSnapshot.objects.filter(pk=request.data.get("snapshot_id"), owner=request.user).first()
        if snapshot is None:
            return Response({"detail": "Snapshot no disponible."}, status=status.HTTP_404_NOT_FOUND)
        export, token = queue_report_export(owner=request.user, snapshot=snapshot, export_format=str(request.data.get("format") or "json"))
        return Response({"id": export.pk, "status": export.status, "download_token": token, "expires_after_ready_seconds": 86400}, status=status.HTTP_202_ACCEPTED)


class ReportExportDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, export_id):
        try:
            export, content = consume_report_export(export_id=export_id, owner=request.user, token=request.headers.get("X-Download-Token", ""))
        except Exception:
            return Response({"detail": "Export no disponible, usado o expirado."}, status=status.HTTP_404_NOT_FOUND)
        extension = "json" if export.export_format == "json" else "csv"
        response = FileResponse(BytesIO(content), content_type="application/json" if extension == "json" else "text/csv")
        response["Content-Disposition"] = f'attachment; filename="vexxo-report-{export.pk}.{extension}"'
        response["Cache-Control"] = "no-store"
        return response
