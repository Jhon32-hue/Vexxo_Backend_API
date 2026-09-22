from __future__ import annotations

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from documents.files.models import DocumentFile
from documents.files.scanner import scan_document
from security.encryption import encrypt_bytes, encryption_status, rewrap_envelope_key


def migrate_historical_documents(*, limit: int = 25) -> dict:
    if not encryption_status()["configured"]:
        return {"configured": False, "migrated": 0, "remaining": DocumentFile.objects.filter(is_encrypted=False, deleted_at__isnull=True).count()}
    migrated = 0
    for document_id in list(DocumentFile.objects.filter(is_encrypted=False, deleted_at__isnull=True).order_by("created_at").values_list("pk", flat=True)[:max(1, min(limit, 100))]):
        with transaction.atomic():
            document = DocumentFile.objects.select_for_update().get(pk=document_id)
            if document.is_encrypted or document.deleted_at is not None:
                continue
            old_name = document.file.name
            with document.file.open("rb") as source:
                plaintext = source.read()
            scan_engine = scan_document(content=plaintext, filename=document.original_name)
            ciphertext, envelope = encrypt_bytes(plaintext, aad=f"document:{document.pk}")
            document.file.save(f"{document.pk}.vexxo", ContentFile(ciphertext), save=False)
            document.is_encrypted = True
            document.encryption_envelope = envelope
            document.scan_status = DocumentFile.ScanStatus.CLEAN
            document.scan_engine = scan_engine
            document.scanned_at = timezone.now()
            document.save(update_fields=["file", "is_encrypted", "encryption_envelope", "scan_status", "scan_engine", "scanned_at", "updated_at"])
            new_name = document.file.name
            if old_name and old_name != new_name:
                transaction.on_commit(lambda name=old_name, storage=document.file.storage: storage.delete(name))
            migrated += 1
    return {"configured": True, "migrated": migrated, "remaining": DocumentFile.objects.filter(is_encrypted=False, deleted_at__isnull=True).count()}


@transaction.atomic
def rotate_document_key(document: DocumentFile, *, target_version: str | None = None) -> DocumentFile:
    document = DocumentFile.objects.select_for_update().get(pk=document.pk)
    if not document.is_encrypted or not document.encryption_envelope:
        raise ValueError("document_not_encrypted")
    document.encryption_envelope = rewrap_envelope_key(
        document.encryption_envelope,
        aad=f"document:{document.pk}",
        target_version=target_version,
    )
    document.save(update_fields=["encryption_envelope", "updated_at"])
    return document
