from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_account_outbox_tracing_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="sync_runtime",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Estado interno del lifecycle de sync. No exponer como metadata de proveedor.",
            ),
        ),
    ]
