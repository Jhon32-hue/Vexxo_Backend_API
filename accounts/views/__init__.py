from rest_framework import viewsets
from accounts.models import Account
from accounts.serializers import CuentaSerializer


class CuentaViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all().order_by('-created_at')
    serializer_class = CuentaSerializer

