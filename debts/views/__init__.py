from rest_framework import viewsets
from debts.models import Debt, DebtInstallment
from debts.serializers import DebtSerializer, DebtInstallmentSerializer


class DebtViewSet(viewsets.ModelViewSet):
    queryset = Debt.objects.all().order_by('-created_at')
    serializer_class = DebtSerializer


class DebtInstallmentViewSet(viewsets.ModelViewSet):
    queryset = DebtInstallment.objects.select_related('debt').all()
    serializer_class = DebtInstallmentSerializer

