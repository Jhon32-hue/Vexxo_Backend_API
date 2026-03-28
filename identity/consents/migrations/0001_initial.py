from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserConsent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("consent_type", models.CharField(choices=[("terms", "Terms"), ("privacy", "Privacy"), ("marketing", "Marketing"), ("open_banking_data", "Open Banking Data"), ("open_banking_payments", "Open Banking Payments"), ("data_export", "Data Export"), ("document_ocr", "Document OCR"), ("ai_processing", "AI Processing")], max_length=32)),
                ("provider", models.CharField(blank=True, default="", max_length=64)),
                ("external_consent_id", models.CharField(blank=True, default="", max_length=128)),
                ("scope_code", models.CharField(blank=True, default="", max_length=128)),
                ("status", models.CharField(choices=[("granted", "Granted"), ("revoked", "Revoked"), ("expired", "Expired"), ("pending", "Pending")], default="pending", max_length=16)),
                ("purpose", models.CharField(blank=True, default="", max_length=255)),
                ("legal_basis", models.CharField(blank=True, default="", max_length=64)),
                ("terms_version", models.CharField(blank=True, default="", max_length=32)),
                ("privacy_version", models.CharField(blank=True, default="", max_length=32)),
                ("granted_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("granted_via", models.CharField(blank=True, default="", max_length=32)),
                ("data_categories", models.JSONField(blank=True, default=list)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="identity_consents", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="userconsent",
            index=models.Index(fields=["user", "consent_type", "status"], name="consents_us_user_id_822cc2_idx"),
        ),
        migrations.AddIndex(
            model_name="userconsent",
            index=models.Index(fields=["provider", "external_consent_id"], name="consents_us_provide_d2262b_idx"),
        ),
        migrations.AddIndex(
            model_name="userconsent",
            index=models.Index(fields=["expires_at"], name="consents_us_expires_268c35_idx"),
        ),
    ]
