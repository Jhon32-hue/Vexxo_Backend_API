from django.core.management.base import BaseCommand

from integrations.credentials.models import IntegrationCredential
from security.encryption import encryption_status
from security.models import KeyRotationJob
from documents.files.models import DocumentFile


class Command(BaseCommand):
    help = "Resume uso de versiones criptograficas y ultimos trabajos de rotacion."

    def handle(self, *args, **options):
        status = encryption_status()
        self.stdout.write(f"active_version={status['active_version'] or 'unset'}")
        self.stdout.write(f"read_versions={','.join(status['read_versions']) or 'none'}")
        versions = {}
        for key_version in IntegrationCredential.objects.values_list("key_version", flat=True):
            versions[key_version] = versions.get(key_version, 0) + 1
        for version, count in sorted(versions.items()):
            self.stdout.write(f"credentials[{version}]={count}")
        document_versions = {}
        for envelope in DocumentFile.objects.filter(is_encrypted=True).values_list("encryption_envelope", flat=True):
            version = str((envelope or {}).get("key_version") or "unknown")
            document_versions[version] = document_versions.get(version, 0) + 1
        for version, count in sorted(document_versions.items()):
            self.stdout.write(f"documents[{version}]={count}")
        for job in KeyRotationJob.objects.order_by("-created_at")[:5]:
            self.stdout.write(
                f"job={job.public_id} from={job.from_version} to={job.to_version} status={job.status} "
                f"processed={job.processed_count} failed={job.failed_count}"
            )
