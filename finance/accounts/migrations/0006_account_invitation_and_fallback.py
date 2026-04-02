from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def backfill_membership_invitations(apps, schema_editor):
    AccountMembership = apps.get_model("accounts", "AccountMembership")
    AccountInvitation = apps.get_model("accounts", "AccountInvitation")

    for membership in AccountMembership.objects.all().iterator():
        if not membership.invitation_sent_at and not membership.accepted_at and not membership.revoked_at:
            continue

        status = "pending"
        is_current = True
        opened_at = None
        accepted_at = membership.accepted_at
        revoked_at = membership.revoked_at

        if membership.accepted_at:
            status = "accepted"
            is_current = False
            opened_at = membership.accepted_at
        elif membership.revoked_at and not membership.is_active:
            status = "revoked"
            is_current = False

        sent_at = membership.invitation_sent_at or membership.accepted_at or membership.revoked_at or timezone.now()

        AccountInvitation.objects.get_or_create(
            membership_id=membership.pk,
            attempt_number=1,
            defaults={
                "account_id": membership.account_id,
                "user_id": membership.user_id,
                "invited_by_id": membership.invited_by_id,
                "token": membership.invitation_token or uuid.uuid4(),
                "status": status,
                "is_current": is_current,
                "channel": "legacy_backfill",
                "sent_at": sent_at,
                "opened_at": opened_at,
                "accepted_at": accepted_at,
                "revoked_at": revoked_at,
                "metadata": {"source": "membership_legacy_fields_backfill"},
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_account_intelligence_layer"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountInvitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("opened", "Opened"), ("accepted", "Accepted"), ("expired", "Expired"), ("revoked", "Revoked")], db_index=True, default="pending", max_length=16)),
                ("attempt_number", models.PositiveIntegerField(default=1)),
                ("is_current", models.BooleanField(db_index=True, default=True)),
                ("channel", models.CharField(blank=True, default="direct_link", max_length=32)),
                ("sent_at", models.DateTimeField(db_index=True, default=timezone.now)),
                ("expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("opened_at", models.DateTimeField(blank=True, null=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="membership_invitations", to="accounts.account")),
                ("invited_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sent_account_invitations", to=settings.AUTH_USER_MODEL)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invitations", to="accounts.accountmembership")),
                ("resend_of", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reissues", to="accounts.accountinvitation")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="account_invitations", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Account invitation",
                "verbose_name_plural": "Account invitations",
            },
        ),
        migrations.CreateModel(
            name="AccountBalanceFallback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("transaction_id", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("reason", models.CharField(db_index=True, max_length=64)),
                ("source", models.CharField(db_index=True, default="accounts.signals.fallback_recalc", max_length=64)),
                ("old_state_present", models.BooleanField(default=False)),
                ("affected_account_ids", models.JSONField(blank=True, default=list)),
                ("old_balance", models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                ("new_balance", models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                ("recalculated", models.BooleanField(db_index=True, default=False)),
                ("delta", models.DecimalField(decimal_places=6, default="0.000000", max_digits=18)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="balance_fallback_events", to="accounts.account")),
            ],
            options={
                "verbose_name": "Account balance fallback",
                "verbose_name_plural": "Account balance fallbacks",
            },
        ),
        migrations.AddIndex(
            model_name="accountinvitation",
            index=models.Index(fields=["membership", "is_current"], name="accinv_member_curr_idx"),
        ),
        migrations.AddIndex(
            model_name="accountinvitation",
            index=models.Index(fields=["user", "status"], name="accinv_user_status_idx"),
        ),
        migrations.AddIndex(
            model_name="accountinvitation",
            index=models.Index(fields=["account", "status"], name="accinv_account_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="accountinvitation",
            constraint=models.UniqueConstraint(condition=models.Q(is_current=True), fields=("membership",), name="uniq_curr_inv_per_membership"),
        ),
        migrations.AddIndex(
            model_name="accountbalancefallback",
            index=models.Index(fields=["account", "created_at"], name="accfb_account_created_idx"),
        ),
        migrations.AddIndex(
            model_name="accountbalancefallback",
            index=models.Index(fields=["reason", "created_at"], name="accfb_reason_created_idx"),
        ),
        migrations.AddIndex(
            model_name="accountbalancefallback",
            index=models.Index(fields=["recalculated", "created_at"], name="accfb_recalc_created_idx"),
        ),
        migrations.RunPython(backfill_membership_invitations, migrations.RunPython.noop),
    ]
