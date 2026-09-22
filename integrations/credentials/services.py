from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from integrations.credentials.models import IntegrationCredential
from security.encryption import decrypt_secret, encrypt_secret, rewrap_secret


@transaction.atomic
def store_credential(*, owner, provider: str, credential_type: str, secret: str, external_reference: str = "", expires_at=None, safe_metadata: dict | None = None) -> IntegrationCredential:
    credential = IntegrationCredential(
        owner=owner,
        provider=provider,
        credential_type=credential_type,
        external_reference=external_reference,
        expires_at=expires_at,
        safe_metadata=safe_metadata or {},
    )
    credential.full_clean(exclude=["encrypted_payload", "key_version"])
    credential.encrypted_payload = encrypt_secret(secret, aad=credential.encryption_aad())
    credential.key_version = credential.encrypted_payload["key_version"]
    credential.save()
    return credential

def reveal_credential(credential: IntegrationCredential) -> str:
    if credential.status != IntegrationCredential.Status.ACTIVE:
        raise ValueError("Credential is not active.")
    if credential.expires_at and credential.expires_at <= timezone.now():
        raise ValueError("Credential has expired.")
    return decrypt_secret(credential.encrypted_payload, aad=credential.encryption_aad())


@transaction.atomic
def revoke_credential(credential: IntegrationCredential) -> IntegrationCredential:
    credential = IntegrationCredential.objects.select_for_update().get(pk=credential.pk)
    credential.status = IntegrationCredential.Status.REVOKED
    credential.revoked_at = timezone.now()
    credential.save(update_fields=["status", "revoked_at", "updated_at"])
    return credential


@transaction.atomic
def rotate_credential_key(credential: IntegrationCredential, *, target_version: str | None = None) -> IntegrationCredential:
    credential = IntegrationCredential.objects.select_for_update().get(pk=credential.pk)
    credential.encrypted_payload = rewrap_secret(
        credential.encrypted_payload,
        aad=credential.encryption_aad(),
        target_version=target_version,
    )
    credential.key_version = credential.encrypted_payload["key_version"]
    credential.last_rotated_at = timezone.now()
    credential.save(update_fields=["encrypted_payload", "key_version", "last_rotated_at", "updated_at"])
    return credential
