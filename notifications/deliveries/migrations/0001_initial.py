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
            name="NotificationDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(choices=[("in_app", "In app"), ("email", "Email"), ("push", "Push"), ("system", "System")], default="in_app", max_length=16)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("delivered", "Delivered"), ("failed", "Failed"), ("read", "Read")], default="pending", max_length=16)),
                ("event_type", models.CharField(blank=True, default="", max_length=128)),
                ("source", models.CharField(blank=True, default="", max_length=128)),
                ("title", models.CharField(max_length=180)),
                ("message", models.TextField()),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("dedupe_key", models.CharField(blank=True, max_length=190, null=True, unique=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notification_deliveries", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="notificationdelivery",
            index=models.Index(fields=["owner", "status"], name="notificatio_owner_i_676488_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationdelivery",
            index=models.Index(fields=["owner", "channel"], name="notificatio_owner_i_fcb8ed_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationdelivery",
            index=models.Index(fields=["owner", "created_at"], name="notificatio_owner_i_60f862_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationdelivery",
            index=models.Index(fields=["event_type", "created_at"], name="notificatio_event_t_6674f3_idx"),
        ),
    ]
