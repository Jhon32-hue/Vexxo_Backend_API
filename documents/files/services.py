from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from documents.files.models import DocumentDownloadGrant, DocumentFile
from documents.files.scanner import scan_document
from documents.metadata.models import DocumentMetadata
from security.encryption import decrypt_bytes, encryption_status, encrypt_bytes


def _sha256(uploaded_file) -> str:
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


@transaction.atomic
def store_document(*, owner, uploaded_file, metadata: dict | None = None, expected_sha256: str = ""):
    max_bytes = int(getattr(settings, "DOCUMENTS_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
    if uploaded_file.size <= 0 or uploaded_file.size > max_bytes:
        raise ValidationError({"file": f"El archivo debe pesar entre 1 y {max_bytes} bytes."})

    checksum = _sha256(uploaded_file)
    expected = str(expected_sha256 or "").strip().lower()
    if expected and expected != checksum:
        raise ValidationError({"sha256": "El checksum enviado no coincide con el archivo."})

    existing = DocumentFile.objects.filter(owner=owner, sha256=checksum, deleted_at__isnull=True).first()
    if existing:
        existing._idempotent_replay = True
        return existing

    original_content = uploaded_file.read()
    uploaded_file.seek(0)
    scan_engine = scan_document(content=original_content, filename=str(uploaded_file.name or "document.bin"))
    document_id = __import__("uuid").uuid4()
    encrypted = encryption_status()["configured"]
    envelope = {}
    stored_file = uploaded_file
    if encrypted:
        ciphertext, envelope = encrypt_bytes(original_content, aad=f"document:{document_id}")
        stored_file = ContentFile(ciphertext, name=f"{uploaded_file.name}.vexxo")

    document = DocumentFile.objects.create(
        id=document_id,
        owner=owner,
        file=stored_file,
        original_name=str(uploaded_file.name or "document.bin")[:255],
        content_type=str(getattr(uploaded_file, "content_type", "") or "")[:128],
        size_bytes=uploaded_file.size,
        sha256=checksum,
        is_encrypted=encrypted,
        encryption_envelope=envelope,
        scan_status=DocumentFile.ScanStatus.CLEAN,
        scan_engine=scan_engine,
        scanned_at=timezone.now(),
    )
    metadata = metadata or {}
    DocumentMetadata.objects.create(
        document=document,
        capture_source=str(metadata.get("capture_source") or "upload")[:32],
        merchant_hint=str(metadata.get("merchant_hint") or "")[:180],
        amount_hint=metadata.get("amount_hint") or None,
        currency_hint=str(metadata.get("currency_hint") or "")[:12],
        attributes=metadata.get("attributes") if isinstance(metadata.get("attributes"), dict) else {},
    )
    document._idempotent_replay = False
    return document


def read_document_plaintext(document: DocumentFile) -> bytes:
    with document.file.open("rb") as source:
        content = source.read()
    if not document.is_encrypted:
        return content
    return decrypt_bytes(content, document.encryption_envelope, aad=f"document:{document.pk}")


@transaction.atomic
def issue_download_grant(*, document: DocumentFile, owner, ttl_seconds: int = 300) -> tuple[DocumentDownloadGrant, str]:
    if document.owner_id != owner.pk or document.deleted_at is not None:
        raise ValidationError({"document": "Documento no disponible."})
    raw_token = secrets.token_urlsafe(32)
    grant = DocumentDownloadGrant.objects.create(
        document=document,
        owner=owner,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=timezone.now() + timedelta(seconds=max(30, min(int(ttl_seconds), 900))),
    )
    return grant, raw_token


@transaction.atomic
def consume_download_grant(*, grant_id, raw_token: str) -> tuple[DocumentDownloadGrant, bytes]:
    grant = DocumentDownloadGrant.objects.select_for_update().select_related("document").filter(pk=grant_id).first()
    supplied_hash = hashlib.sha256(str(raw_token or "").encode("utf-8")).hexdigest()
    if (
        grant is None
        or grant.consumed_at is not None
        or grant.expires_at <= timezone.now()
        or not secrets.compare_digest(grant.token_hash, supplied_hash)
        or grant.document.deleted_at is not None
    ):
        raise ValidationError({"token": "Grant invalido, usado o expirado."})
    content = read_document_plaintext(grant.document)
    grant.consumed_at = timezone.now()
    grant.save(update_fields=["consumed_at"])
    return grant, content


@transaction.atomic
def soft_delete_document(*, document: DocumentFile, owner) -> DocumentFile:
    locked = DocumentFile.objects.select_for_update().get(pk=document.pk, owner=owner)
    if locked.deleted_at is None:
        locked.deleted_at = timezone.now()
        locked.retention_expires_at = locked.deleted_at + timedelta(
            days=max(1, int(getattr(settings, "DOCUMENTS_DELETED_RETENTION_DAYS", 30)))
        )
        locked.status = DocumentFile.Status.DELETED
        locked.save(update_fields=["deleted_at", "retention_expires_at", "status", "updated_at"])
    return locked


def purge_expired_documents(*, now=None, limit: int = 100) -> dict:
    now = now or timezone.now()
    document_ids = list(
        DocumentFile.objects.filter(
            deleted_at__isnull=False,
            retention_expires_at__lte=now,
            legal_hold=False,
            purged_at__isnull=True,
        )
        .order_by("retention_expires_at")
        .values_list("pk", flat=True)[: max(1, min(int(limit), 1000))]
    )
    purged = 0
    for document_id in document_ids:
        with transaction.atomic():
            document = DocumentFile.objects.select_for_update().filter(pk=document_id, purged_at__isnull=True).first()
            if document is None or document.legal_hold:
                continue
            document.file.delete(save=False)
            document.file.name = ""
            document.original_name = "purged"
            document.content_type = ""
            document.size_bytes = 0
            document.encryption_envelope = {}
            document.purged_at = now
            document.save(
                update_fields=[
                    "file", "original_name", "content_type", "size_bytes", "encryption_envelope", "purged_at", "updated_at",
                ]
            )
            document.ocr_requests.update(
                client_extracted_text="",
                client_structured_hint={},
                extracted_text="",
                structured_data={},
                last_error="",
            )
            if hasattr(document, "document_metadata"):
                metadata = document.document_metadata
                metadata.merchant_hint = ""
                metadata.amount_hint = None
                metadata.currency_hint = ""
                metadata.attributes = {}
                metadata.save()
            purged += 1
    return {"purged_documents": purged}
