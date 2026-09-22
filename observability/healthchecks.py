from __future__ import annotations

from django.db import connection


def database_health() -> dict:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"ok": True, "backend": connection.vendor}
    except Exception as exc:
        return {"ok": False, "backend": connection.vendor, "error": exc.__class__.__name__}


def runtime_health() -> dict:
    database = database_health()
    return {"ok": bool(database["ok"]), "checks": {"database": database}}
