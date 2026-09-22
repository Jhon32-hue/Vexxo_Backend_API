from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from identity.devices.models import DevicePlatformAttestationChallenge, UserDevice
from identity.devices.services import revoke_platform_attestations


class Command(BaseCommand):
    help = "Revoca attestations masivamente y cierra sesiones de los dispositivos afectados."

    def add_arguments(self, parser):
        parser.add_argument("--provider", choices=DevicePlatformAttestationChallenge.Provider.values, default="")
        parser.add_argument("--older-than-days", type=int, default=0)
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options["older_than_days"]) if options["older_than_days"] else None
        queryset = UserDevice.objects.filter(attestation_status="platform_verified")
        if options["provider"]:
            queryset = queryset.filter(attestation_provider=options["provider"])
        if cutoff:
            queryset = queryset.filter(platform_verified_at__lt=cutoff)
        count = queryset.count()
        self.stdout.write(f"matching_devices={count}")
        if not options["confirm"]:
            self.stdout.write("dry_run=true")
            return
        if not options["provider"] and not cutoff:
            raise CommandError("La revocacion global requiere --provider o --older-than-days como guardrail.")
        revoked = revoke_platform_attestations(provider=options["provider"], verified_before=cutoff)
        self.stdout.write(f"revoked_devices={revoked}")
