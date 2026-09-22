"""Reminder job boundary.

Concrete reminder jobs must expose an idempotent service function and be
registered in ``tasks.scheduled.registry``. This module intentionally contains
no runtime job yet.
"""
