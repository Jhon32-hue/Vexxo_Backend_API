from django.db import models

from common.models import StandardDomainEventOutbox


class DebtDomainEventOutbox(StandardDomainEventOutbox):
    class Meta(StandardDomainEventOutbox.Meta):
        abstract = False
        indexes = [
            models.Index(fields=["status", "occurred_at"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["aggregate_type", "aggregate_id"]),
            models.Index(fields=["correlation_id"]),
            models.Index(fields=["request_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(retry_count__gte=0),
                name="debt_outbox_retry_count_non_negative",
            )
        ]
