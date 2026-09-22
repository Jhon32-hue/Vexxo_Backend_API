from rest_framework import serializers
from finance.categories.models import Category


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ("owner",)
