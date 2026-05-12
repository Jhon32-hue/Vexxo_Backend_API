from datetime import date
from django.db.models import Sum
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from finance.budgets.services import build_budget_monthly_overview
from finance.transactions.Models import Transaction


class CashflowView(APIView):
    def get(self, request):
        start = request.query_params.get('desde')
        end = request.query_params.get('hasta')
        qs = Transaction.objects.all()
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
    def get(self, request):
        period = request.query_params.get('periodo', 'mes')
        qs = Transaction.objects.filter(type='expense')
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
