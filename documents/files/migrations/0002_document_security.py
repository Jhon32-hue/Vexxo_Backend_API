from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("files", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="documentfile", name="encryption_envelope", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="documentfile", name="is_encrypted", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="documentfile", name="scan_engine", field=models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField(model_name="documentfile", name="scan_status", field=models.CharField(choices=[("pending", "Pending"), ("clean", "Clean"), ("infected", "Infected"), ("failed", "Failed")], db_index=True, default="pending", max_length=16)),
        migrations.AddField(model_name="documentfile", name="scanned_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.CreateModel(
            name="DocumentDownloadGrant",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="download_grants", to="files.documentfile")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="document_download_grants", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
