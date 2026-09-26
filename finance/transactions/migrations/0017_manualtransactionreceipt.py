from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("transactions", "0016_transactionexternaldetails_classification_source_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.CreateModel(
        name="ManualTransactionReceipt",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("key_hash", models.CharField(max_length=64)),
            ("payload_hash", models.CharField(max_length=64)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("actor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ("transaction", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="transactions.transaction")),
        ],
        options={"constraints": [models.UniqueConstraint(fields=("actor", "key_hash"), name="unique_manual_receipt_actor_key")]},
    )]
