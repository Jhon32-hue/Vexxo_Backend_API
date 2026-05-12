from rest_framework import serializers


class ThresholdListField(serializers.ListField):
    child = serializers.IntegerField(min_value=1, max_value=100)


class BudgetListQuerySerializer(serializers.Serializer):
    month = serializers.CharField(required=False)


class CategoryBudgetListQuerySerializer(BudgetListQuerySerializer):
    category = serializers.IntegerField(required=False)


class SharedBudgetListQuerySerializer(BudgetListQuerySerializer):
    team = serializers.IntegerField(required=False)


class CategoryBudgetWriteSerializer(serializers.Serializer):
    month = serializers.CharField(required=False)
    category = serializers.IntegerField(required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    alert_thresholds = ThresholdListField(required=False)


class CategoryBudgetBulkItemSerializer(serializers.Serializer):
    category = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    alert_thresholds = ThresholdListField(required=False)


class CategoryBudgetPeriodOperationSerializer(serializers.Serializer):
    month = serializers.CharField()
    items = CategoryBudgetBulkItemSerializer(many=True)


class SharedBudgetWriteSerializer(serializers.Serializer):
    team = serializers.IntegerField(required=False)
    name = serializers.CharField(required=False, max_length=160)
    month = serializers.CharField(required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    alert_thresholds = ThresholdListField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class SharedBudgetTransactionLinkSerializer(serializers.Serializer):
    transaction_id = serializers.IntegerField()


class SharedBudgetTemplateLinkSerializer(serializers.Serializer):
    payment_template_id = serializers.IntegerField()
