from __future__ import annotations

from security.validators import validate_ordering


def safe_order_by(queryset, ordering: str, *, allowed_fields: set[str]):
    """Apply dynamic ordering only after an explicit field allowlist check."""
    return queryset.order_by(validate_ordering(ordering, allowed_fields=allowed_fields))
