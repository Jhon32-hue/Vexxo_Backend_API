from rest_framework import serializers
from finance.fx.models import FXRate


class TasaFXSerializer(serializers.ModelSerializer):
    class Meta:
        model = FXRate
        fields = '__all__'
