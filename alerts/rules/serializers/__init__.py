from rest_framework import serializers
from alerts.rules.models import Rule


class ReglaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rule
        fields = '__all__'
