from __future__ import annotations

from django.db import transaction
from django.db.models import F

from integrations.open_banking.contracts import normalize_merchant_alias

from finance.vendors.models import VendorAlias


@transaction.atomic
def record_vendor_alias_suggestion(*, owner, merchant_name: str, source: str, confidence_score: int = 70):
    normalized = normalize_merchant_alias(merchant_name)
    if not normalized:
        return None
    alias, created = VendorAlias.objects.select_for_update().get_or_create(
        owner=owner,
        normalized_alias=normalized,
        defaults={
            "display_name": str(merchant_name or "")[:180],
            "source": str(source or "transaction_intake")[:64],
            "confidence_score": max(0, min(int(confidence_score), 100)),
        },
    )
    if not created:
        VendorAlias.objects.filter(pk=alias.pk).update(occurrence_count=F("occurrence_count") + 1)
        alias.refresh_from_db()
    return alias
