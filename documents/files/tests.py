from datetime import timedelta
import base64
import os

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from documents.files.models import DocumentFile
from documents.files.migration_service import rotate_document_key
from documents.files.services import purge_expired_documents, read_document_plaintext, soft_delete_document
from security.encryption import encrypt_bytes
from documents.ocr_requests.models import DocumentDomainEventOutbox, OcrFieldObservation, OcrRequest
from documents.ocr_requests.services import process_ocr_batch


User = get_user_model()
KEY_V1 = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
KEY_V2 = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


class DocumentFlowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="documents-owner", email="documents@example.com", password="secret123A"
        )
        self.other = User.objects.create_user(
            username="documents-other", email="documents-other@example.com", password="secret123A"
        )
        self.client.force_authenticate(self.user)

    def _upload(self, content=b"merchant: Vexxo\namount: 12000"):
        return self.client.post(
            "/api/documents/files/",
            {"file": SimpleUploadedFile("receipt.txt", content, content_type="text/plain")},
            format="multipart",
        )

    def test_upload_is_checksum_idempotent_and_owner_scoped(self):
        first = self._upload()
        second = self._upload()
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(DocumentFile.objects.filter(owner=self.user).count(), 1)

        foreign = DocumentFile.objects.create(
            owner=self.other,
            file=SimpleUploadedFile("other.txt", b"private"),
            original_name="other.txt",
            content_type="text/plain",
            size_bytes=7,
            sha256="a" * 64,
        )
        response = self.client.get(f"/api/documents/files/{foreign.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_ocr_request_is_durable_idempotent_and_emits_outbox(self):
        upload = self._upload()
        url = f"/api/documents/files/{upload.data['id']}/request-ocr/"
        first = self.client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="ocr-1")
        second = self.client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="ocr-1")
        self.assertEqual(first.status_code, 202, first.data)
        self.assertEqual(second.status_code, 200, second.data)

        summary = process_ocr_batch(limit=10, worker_id="test")
        self.assertEqual(summary["succeeded"], 1)
        request = OcrRequest.objects.get(pk=first.data["id"])
        self.assertEqual(request.status, OcrRequest.Status.SUCCEEDED)
        self.assertIn("merchant", request.extracted_text)
        self.assertTrue(DocumentDomainEventOutbox.objects.filter(aggregate_id=str(request.pk)).exists())

    def test_ocr_worker_recovers_stale_processing_lock(self):
        upload = self._upload(b"merchant: stale lock")
        response = self.client.post(
            f"/api/documents/files/{upload.data['id']}/request-ocr/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ocr-stale",
        )
        request = OcrRequest.objects.get(pk=response.data["id"])
        request.status = OcrRequest.Status.PROCESSING
        request.locked_at = timezone.now() - timedelta(minutes=16)
        request.locked_by = "dead-worker"
        request.save(update_fields=["status", "locked_at", "locked_by", "updated_at"])

        summary = process_ocr_batch(limit=10, worker_id="replacement-worker")

        request.refresh_from_db()
        self.assertEqual(summary["succeeded"], 1)
        self.assertEqual(request.status, OcrRequest.Status.SUCCEEDED)
        self.assertEqual(request.locked_by, "")

    def test_download_grant_is_one_time(self):
        upload = self._upload(b"private report")
        issued = self.client.post(f"/api/documents/files/{upload.data['id']}/download-grant/", {}, format="json")
        self.assertEqual(issued.status_code, 201, issued.data)
        url = f"/api/documents/downloads/{issued.data['grant_id']}/"
        first = self.client.get(url, HTTP_X_DOWNLOAD_TOKEN=issued.data["token"])
        self.assertEqual(first.status_code, 200)
        second = self.client.get(url, HTTP_X_DOWNLOAD_TOKEN=issued.data["token"])
        self.assertEqual(second.status_code, 404)

    def test_antivirus_policy_rejects_eicar(self):
        response = self._upload(
            b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(
        SECURITY_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
        SECURITY_ENCRYPTION_KEYS={"v1": KEY_V1, "v2": KEY_V2},
    )
    def test_document_dek_can_be_rewrapped_without_rewriting_ciphertext(self):
        document_id = __import__("uuid").uuid4()
        ciphertext, envelope = encrypt_bytes(b"historical-private-file", aad=f"document:{document_id}")
        document = DocumentFile.objects.create(
            id=document_id,
            owner=self.user,
            file=ContentFile(ciphertext, name="encrypted.vexxo"),
            original_name="encrypted.txt",
            content_type="text/plain",
            size_bytes=23,
            sha256="b" * 64,
            is_encrypted=True,
            encryption_envelope=envelope,
        )
        original_file_name = document.file.name
        rotate_document_key(document, target_version="v2")
        document.refresh_from_db()
        self.assertEqual(document.encryption_envelope["key_version"], "v2")
        self.assertEqual(document.file.name, original_file_name)
        self.assertEqual(read_document_plaintext(document), b"historical-private-file")

    def test_deleted_document_is_physically_purged_after_retention(self):
        upload = self._upload(b"purge after retention")
        document = DocumentFile.objects.get(pk=upload.data["id"])
        storage = document.file.storage
        stored_name = document.file.name
        self.assertTrue(storage.exists(stored_name))
        soft_delete_document(document=document, owner=self.user)
        DocumentFile.objects.filter(pk=document.pk).update(
            retention_expires_at=timezone.now() - timedelta(seconds=1)
        )
        summary = purge_expired_documents()
        document.refresh_from_db()
        self.assertEqual(summary["purged_documents"], 1)
        self.assertFalse(storage.exists(stored_name))
        self.assertEqual(document.file.name, "")
        self.assertIsNotNone(document.purged_at)
        self.assertEqual(document.sha256, upload.data["sha256"])

    def test_ocr_user_correction_keeps_field_lineage(self):
        upload = self._upload(b"merchant: initial")
        requested = self.client.post(
            f"/api/documents/files/{upload.data['id']}/request-ocr/",
            {"client_structured_hint": {"merchant": "Initial store"}},
            format="json",
            HTTP_IDEMPOTENCY_KEY="ocr-correction-001",
        )
        process_ocr_batch(limit=10, worker_id="test-correction")
        first = OcrFieldObservation.objects.get(
            request_id=requested.data["id"],
            field_name="merchant",
        )
        corrected = self.client.post(
            f"/api/documents/files/{upload.data['id']}/ocr-corrections/",
            {
                "ocr_request": requested.data["id"],
                "field_name": "merchant",
                "value": "Corrected store",
                "notes": "User verified the receipt",
            },
            format="json",
        )
        self.assertEqual(corrected.status_code, 201, corrected.data)
        self.assertEqual(corrected.data["supersedes"], first.pk)
        request = OcrRequest.objects.get(pk=requested.data["id"])
        self.assertEqual(request.structured_data["merchant"], "Corrected store")
