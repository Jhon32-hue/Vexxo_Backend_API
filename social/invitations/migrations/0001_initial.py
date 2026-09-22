import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("teams", "0002_team_updated_at_membership_updated_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeamInvitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("email", models.EmailField(max_length=254)),
                ("role", models.CharField(choices=[("accountant", "accountant"), ("viewer", "viewer")], max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("opened", "Opened"), ("accepted", "Accepted"), ("expired", "Expired"), ("revoked", "Revoked")], db_index=True, default="pending", max_length=16)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=160)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("opened_at", models.DateTimeField(blank=True, null=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("invited_by", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sent_team_invitations", to=settings.AUTH_USER_MODEL)),
                ("invited_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="team_invitations", to=settings.AUTH_USER_MODEL)),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invitations", to="teams.team")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="teaminvitation", index=models.Index(fields=["team", "status"], name="invitations_team_id_697f22_idx")),
        migrations.AddIndex(model_name="teaminvitation", index=models.Index(fields=["email", "status"], name="invitations_email_827d77_idx")),
        migrations.AddIndex(model_name="teaminvitation", index=models.Index(fields=["invited_user", "status"], name="invitations_invited_b008b2_idx")),
        migrations.AddConstraint(model_name="teaminvitation", constraint=models.UniqueConstraint(condition=models.Q(("status__in", ["pending", "opened"])), fields=("team", "email"), name="uniq_active_team_invitation_email")),
        migrations.AddConstraint(model_name="teaminvitation", constraint=models.UniqueConstraint(condition=models.Q(("idempotency_key", ""), _negated=True), fields=("invited_by", "idempotency_key"), name="uniq_team_invitation_idempotency")),
    ]
