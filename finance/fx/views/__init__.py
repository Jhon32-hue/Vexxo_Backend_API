from rest_framework import viewsets
from finance.fx.models import FXRate
from finance.fx.serializers import TasaFXSerializer


class TasaFXViewSet(viewsets.ModelViewSet):
    queryset = FXRate.objects.all().order_by('-date')
    serializer_class = TasaFXSerializer
