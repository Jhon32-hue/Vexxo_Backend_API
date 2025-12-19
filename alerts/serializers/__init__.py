from rest_framework import serializers
from alerts.models import Alert


class AlertaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = '__all__'

