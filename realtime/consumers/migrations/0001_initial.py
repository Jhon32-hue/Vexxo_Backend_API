from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RealtimeSignal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("owner_id", models.PositiveBigIntegerField(db_index=True)),
                ("channel", models.CharField(default="accounts", max_length=64)),
                ("event", models.CharField(max_length=128)),
                ("aggregate_type", models.CharField(blank=True, default="", max_length=64)),
                ("aggregate_id", models.CharField(blank=True, default="", max_length=64)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="realtimesignal",
            index=models.Index(fields=["owner_id", "channel", "created_at"], name="realtime_c_owner_i_624a9a_idx"),
        ),
        migrations.AddIndex(
            model_name="realtimesignal",
            index=models.Index(fields=["event", "created_at"], name="realtime_c_event_4c36df_idx"),
        ),
    ]
