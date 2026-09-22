from rest_framework import serializers

from documents.files.models import DocumentFile
from documents.links_to_transactions.models import DocumentTransactionLink
from finance.transactions.Models import Transaction


class DocumentTransactionLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentTransactionLink
        fields = ["id", "document", "transaction", "relationship", "created_at"]
        read_only_fields = ["id", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["document"].queryset = DocumentFile.objects.filter(
                owner=request.user, deleted_at__isnull=True
            )
            self.fields["transaction"].queryset = Transaction.objects.filter(owner=request.user)

    def create(self, validated_data):
        return DocumentTransactionLink.objects.create(owner=self.context["request"].user, **validated_data)
