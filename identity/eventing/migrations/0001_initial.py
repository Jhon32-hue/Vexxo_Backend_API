from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="IdentityDomainEventOutbox",
            fields=[
                ("id", models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ("aggregate_type", models.CharField(max_length=64)),
                ("aggregate_id", models.CharField(max_length=64)),
                ("event_type", models.CharField(max_length=128)),
                ("idempotency_key", models.CharField(max_length=160, unique=True)),
                ("payload", models.JSONField(default=dict)),
                ("metadata", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("published", "Published"), ("failed", "Failed")], default="pending", max_length=16)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("locked_by", models.CharField(blank=True, default="", max_length=64)),
            ],
            options={"ordering": ["occurred_at"]},
        ),
        migrations.AddIndex(
            model_name="identitydomaineventoutbox",
            index=models.Index(fields=["status", "occurred_at"], name="identity_ev_status_356d94_idx"),
        ),
        migrations.AddIndex(
            model_name="identitydomaineventoutbox",
            index=models.Index(fields=["event_type", "occurred_at"], name="identity_ev_event_t_a8a2bf_idx"),
        ),
        migrations.AddIndex(
            model_name="identitydomaineventoutbox",
            index=models.Index(fields=["aggregate_type", "aggregate_id"], name="identity_ev_aggrega_135f5f_idx"),
        ),
        migrations.AddConstraint(
            model_name="identitydomaineventoutbox",
            constraint=models.CheckConstraint(check=models.Q(("retry_count__gte", 0)), name="identity_outbox_retry_count_non_negative"),
        ),
    ]
