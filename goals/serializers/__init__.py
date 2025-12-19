from rest_framework import serializers
from goals.models import Goal


class MetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Goal
        fields = '__all__'

