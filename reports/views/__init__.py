from datetime import date
from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from transactions.Models import Transaction


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

