from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="ReportSnapshot", fields=[("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("report_type", models.CharField(choices=[("cashflow", "Cashflow"), ("expenses_by_category", "Expenses by category")], max_length=40)), ("period_start", models.DateField()), ("period_end", models.DateField()), ("currency", models.CharField(default="COP", max_length=3)), ("timezone_name", models.CharField(default="America/Bogota", max_length=64)), ("as_of", models.DateTimeField()), ("schema_version", models.PositiveSmallIntegerField(default=1)), ("payload", models.JSONField(default=dict)), ("payload_sha256", models.CharField(db_index=True, max_length=64)), ("idempotency_key", models.CharField(max_length=128)), ("created_at", models.DateTimeField(auto_now_add=True)), ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="report_snapshots", to=settings.AUTH_USER_MODEL))], options={"ordering": ["-created_at"]}), migrations.AddConstraint(model_name="reportsnapshot", constraint=models.UniqueConstraint(fields=("owner", "idempotency_key"), name="unique_owner_report_snapshot_key"))]
