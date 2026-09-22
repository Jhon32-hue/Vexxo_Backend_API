import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from documents.files.migration_service import rotate_document_key
from documents.files.models import DocumentFile
from integrations.credentials.models import IntegrationCredential
from integrations.credentials.services import rotate_credential_key
from security.encryption import active_key_version, configured_keyring
from security.models import KeyRotationJob


class Command(BaseCommand):
    help = "Reenvuelve DEKs de credenciales y documentos en lotes usando la llave activa."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--sleep-seconds", type=int, default=5)
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument("--worker-id", default="")

    def handle(self, *args, **options):
        target = active_key_version()
        if not target or target not in configured_keyring():
            raise CommandError("Configure SECURITY_ENCRYPTION_ACTIVE_KEY_VERSION and its key before rotating.")
        while True:
            processed = self._run_batch(target=target, limit=max(1, int(options["limit"])))
            if not options["loop"] or processed == 0:
                break
            time.sleep(max(1, int(options["sleep_seconds"])))

    def _run_batch(self, *, target: str, limit: int) -> int:
        credentials = list(IntegrationCredential.objects.exclude(key_version=target).order_by("pk")[:limit])
        remaining = max(0, limit - len(credentials))
        documents = list(
            DocumentFile.objects.filter(is_encrypted=True)
            .exclude(encryption_envelope__key_version=target)
            .order_by("pk")[:remaining]
        )
        if not credentials and not documents:
            self.stdout.write("rotation_pending=0")
            return 0
        source_versions = {
            *(credential.key_version for credential in credentials),
            *(str(document.encryption_envelope.get("key_version") or "unknown") for document in documents),
        }
        job = KeyRotationJob.objects.create(
            from_version=",".join(sorted(source_versions)),
            to_version=target,
            status=KeyRotationJob.Status.RUNNING,
            started_at=timezone.now(),
        )
        for credential in credentials:
            try:
                rotate_credential_key(credential, target_version=target)
                job.processed_count += 1
            except Exception as exc:
                job.failed_count += 1
                job.last_error = str(exc)[:255]
        for document in documents:
            try:
                rotate_document_key(document, target_version=target)
                job.processed_count += 1
            except Exception as exc:
                job.failed_count += 1
                job.last_error = str(exc)[:255]
        job.status = KeyRotationJob.Status.FAILED if job.failed_count else KeyRotationJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["processed_count", "failed_count", "last_error", "status", "completed_at", "updated_at"])
        self.stdout.write(
            f"rotation_processed={job.processed_count} rotation_failed={job.failed_count} "
            f"credentials={len(credentials)} documents={len(documents)}"
        )
        return job.processed_count
