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
            name="NotificationPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("in_app_enabled", models.BooleanField(default=True)),
                ("push_enabled", models.BooleanField(default=True)),
                ("email_notifications_enabled", models.BooleanField(default=True)),
                ("email_marketing_enabled", models.BooleanField(default=False)),
                ("newsletter_subscribed", models.BooleanField(default=False)),
                ("welcome_email_sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="notification_preferences", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["owner_id"],
                "verbose_name": "Preferencia de notificacion",
                "verbose_name_plural": "Preferencias de notificacion",
            },
        ),
    ]
