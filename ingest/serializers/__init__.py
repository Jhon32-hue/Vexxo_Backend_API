from rest_framework import serializers


class IngestaTextoSerializer(serializers.Serializer):
    texto = serializers.CharField()

