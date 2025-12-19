from rest_framework import serializers
from debts.models import Debt, DebtInstallment


class DebtSerializer(serializers.ModelSerializer):
    class Meta:
        model = Debt
        fields = '__all__'


class DebtInstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtInstallment
        fields = '__all__'

