from __future__ import annotations

from django.db import models


class BudgetScope(models.TextChoices):
    NONE = "none", "No budget"
    PERSONAL = "personal", "Personal budget"
    SHARED = "shared", "Shared budget"


class BudgetAttributionSource(models.TextChoices):
    SYSTEM_DEFAULT = "system_default", "System default"
    MANUAL = "manual", "Manual"
    SUGGESTED_RULE = "suggested_rule", "Suggested rule"
    INHERITED_FROM_TEMPLATE = "inherited_from_template", "Inherited from template"
    LINKED_AFTER_CREATION = "linked_after_creation", "Linked after creation"


__all__ = [
    "BudgetScope",
    "BudgetAttributionSource",
]
