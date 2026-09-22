from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [("snapshots", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="ReportExport", fields=[("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("export_format", models.CharField(choices=[("json", "JSON"), ("csv", "CSV")], default="json", max_length=12)), ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("ready", "Ready"), ("downloaded", "Downloaded"), ("expired", "Expired"), ("failed", "Failed")], db_index=True, default="pending", max_length=16)), ("encrypted_content", models.BinaryField(blank=True, default=bytes)), ("encryption_envelope", models.JSONField(blank=True, default=dict)), ("plaintext_sha256", models.CharField(blank=True, default="", max_length=64)), ("download_token_hash", models.CharField(blank=True, db_index=True, default="", max_length=64)), ("expires_at", models.DateTimeField(blank=True, db_index=True, null=True)), ("downloaded_at", models.DateTimeField(blank=True, null=True)), ("attempt_count", models.PositiveSmallIntegerField(default=0)), ("last_error", models.TextField(blank=True, default="")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="report_exports", to=settings.AUTH_USER_MODEL)), ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="exports", to="snapshots.reportsnapshot"))], options={"ordering": ["-created_at"]})]
