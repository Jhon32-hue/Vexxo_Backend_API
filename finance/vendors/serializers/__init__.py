from rest_framework import serializers
from finance.vendors.models import Vendor


class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = '__all__'
