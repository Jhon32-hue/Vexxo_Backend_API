from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

ZERO = Decimal("0.00")
TWOPLACES = Decimal("0.01")


def quantize_money(value, *, field_label: str, allow_null: bool = True):
    if value in (None, ""):
        if allow_null:
            return None
        return ZERO
    try:
        return Decimal(str(value)).quantize(TWOPLACES)
    except (InvalidOperation, TypeError, ValueError):
        raise serializers.ValidationError(_("%(field)s invalido.") % {"field": field_label})
