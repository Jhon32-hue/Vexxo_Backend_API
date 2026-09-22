from __future__ import annotations

import hashlib
from contextlib import contextmanager

from django.db import connection


def advisory_lock_key(name: str) -> int:
    digest = hashlib.sha256(str(name).encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


@contextmanager
def postgres_advisory_lock(name: str):
    """Try a session-level lock without waiting for another scheduler."""

    if connection.vendor != "postgresql":
        yield True
        return

    key = advisory_lock_key(name)
    acquired = False
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        acquired = bool(cursor.fetchone()[0])
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
