"""Debt lifecycle is intentionally orchestrated by explicit services.

This module remains import-compatible for older code, but it must not register
model signals. Financial transitions belong to ``finance.debts.services`` and
transaction domain-event handlers.
"""
