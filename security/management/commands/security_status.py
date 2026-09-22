from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from integrations.credentials.models import IntegrationCredential
from security.encryption import encryption_status
from security.models import SecurityAuditEvent, SecurityThrottleBucket


class Command(BaseCommand):
    help = "Muestra el estado de los controles transversales de seguridad sin exponer secretos."

    def handle(self, *args, **options):
        encryption = encryption_status()
        jwt_separated = settings.SIMPLE_JWT["SIGNING_KEY"] != settings.SECRET_KEY
        recovery_separated = settings.IDENTITY_RECOVERY_HASH_KEY != settings.SECRET_KEY
        throttle_separated = settings.SECURITY_THROTTLE_HASH_KEY != settings.SECRET_KEY
        active_blocks = SecurityThrottleBucket.objects.filter(blocked_until__gt=timezone.now()).count()
        self.stdout.write(f"encryption_configured={str(encryption['configured']).lower()}")
        self.stdout.write(f"encryption_active_version={encryption['active_version'] or 'unset'}")
        self.stdout.write(f"encryption_read_versions={','.join(encryption['read_versions']) or 'none'}")
        self.stdout.write(f"jwt_key_separated={str(jwt_separated).lower()}")
        self.stdout.write(f"jwt_active_key_version={settings.JWT_KEYRING['ACTIVE_KEY_VERSION']}")
        self.stdout.write(f"jwt_read_versions={','.join(sorted(settings.JWT_KEYRING['SIGNING_KEYS']))}")
        self.stdout.write(f"documents_scanner_backend={settings.DOCUMENTS_SCANNER_BACKEND}")
        self.stdout.write("activation_details=python manage.py security_activation_check")
        self.stdout.write("json_field_audit=python manage.py json_field_audit --details")
        self.stdout.write(f"recovery_hash_key_separated={str(recovery_separated).lower()}")
        self.stdout.write(f"throttle_hash_key_separated={str(throttle_separated).lower()}")
        self.stdout.write(f"active_throttle_blocks={active_blocks}")
        self.stdout.write(f"active_integration_credentials={IntegrationCredential.objects.filter(status='active').count()}")
        self.stdout.write(f"security_events_24h={SecurityAuditEvent.objects.filter(created_at__gte=timezone.now()-timedelta(hours=24)).count()}")
