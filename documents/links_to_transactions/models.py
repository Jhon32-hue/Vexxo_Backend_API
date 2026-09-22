from django.conf import settings
from django.db import models


class DocumentTransactionLink(models.Model):
    class Relationship(models.TextChoices):
        RECEIPT = "receipt", "Receipt"
        INVOICE = "invoice", "Invoice"
        SUPPORTING = "supporting", "Supporting document"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="document_transaction_links",
    )
    document = models.ForeignKey(
        "files.DocumentFile",
        on_delete=models.CASCADE,
        related_name="transaction_links",
    )
    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.CASCADE,
        related_name="document_links",
    )
    relationship = models.CharField(
        max_length=24,
        choices=Relationship.choices,
        default=Relationship.RECEIPT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "transaction", "relationship"],
                name="document_transaction_relationship_unique",
            )
        ]
