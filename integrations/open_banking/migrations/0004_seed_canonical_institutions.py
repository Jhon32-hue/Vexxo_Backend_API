from django.db import migrations


def seed_institutions(apps, schema_editor):
    Institution = apps.get_model("open_banking", "OpenBankingInstitution")
    ProviderInstitution = apps.get_model("open_banking", "OpenBankingProviderInstitution")
    local, _ = Institution.objects.update_or_create(
        code="vexxo-local-development",
        defaults={
            "name": "Banco local de desarrollo",
            "country": "CO",
            "logo_license": "internal-development-only",
            "logo_provenance": "vexxo",
            "is_active": True,
        },
    )
    Institution.objects.update_or_create(
        code="bancolombia-co",
        defaults={
            "name": "Bancolombia",
            "country": "CO",
            "logo_license": "pending-verification",
            "logo_provenance": "manual-canonical-catalog",
            "is_active": True,
        },
    )
    ProviderInstitution.objects.update_or_create(
        provider="local_mock",
        provider_institution_id="vexxo-local-development",
        defaults={
            "institution": local,
            "provider_name": "Banco local de desarrollo",
            "is_active": True,
        },
    )


def unseed_institutions(apps, schema_editor):
    Institution = apps.get_model("open_banking", "OpenBankingInstitution")
    Institution.objects.filter(code__in=["vexxo-local-development", "bancolombia-co"]).delete()


class Migration(migrations.Migration):
    dependencies = [("open_banking", "0003_openbankingconnection_credential_expires_at_and_more")]

    operations = [migrations.RunPython(seed_institutions, unseed_institutions)]
