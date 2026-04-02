from django.db import migrations


def backfill_memberships(apps, schema_editor):
    Account = apps.get_model("accounts", "Account")
    AccountMembership = apps.get_model("accounts", "AccountMembership")

    for account in Account.objects.all().iterator(chunk_size=500):
        AccountMembership.objects.get_or_create(
            account_id=account.id,
            user_id=account.owner_id,
            defaults={
                "role": "owner",
                "access_mode": "full",
                "can_post_transactions": True,
                "can_manage_members": True,
                "can_manage_account_settings": True,
                "can_view_analytics": True,
                "is_active": True,
            },
        )

        shared_user_id = getattr(account, "shared_from_user_id", None)
        if not shared_user_id:
            continue
        if shared_user_id == account.owner_id:
            continue

        AccountMembership.objects.get_or_create(
            account_id=account.id,
            user_id=shared_user_id,
            defaults={
                "role": "viewer",
                "access_mode": "watch_only",
                "can_post_transactions": False,
                "can_manage_members": False,
                "can_manage_account_settings": False,
                "can_view_analytics": True,
                "is_active": True,
                "invited_by_id": account.owner_id,
            },
        )


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_memberships, noop_reverse),
    ]
