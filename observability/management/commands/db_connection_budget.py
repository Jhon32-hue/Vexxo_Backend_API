import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise CommandError(f"{name} debe ser un entero.") from exc
    if value < 0:
        raise CommandError(f"{name} no puede ser negativo.")
    return value


class Command(BaseCommand):
    help = "Valida el presupuesto declarado de conexiones contra PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        api_budget = _positive_int("API_DB_CONNECTION_BUDGET", 8)
        background_budget = _positive_int("BACKGROUND_DB_CONNECTION_BUDGET", 12)
        operational_reserve = _positive_int("DB_OPERATIONAL_CONNECTION_RESERVE", 20)

        with connection.cursor() as cursor:
            cursor.execute("SHOW max_connections")
            max_connections = int(cursor.fetchone()[0])
            cursor.execute("SHOW superuser_reserved_connections")
            superuser_reserved = int(cursor.fetchone()[0])
            cursor.execute(
                """
                SELECT count(*) FILTER (WHERE state = 'active'),
                       count(*) FILTER (WHERE state = 'idle'),
                       count(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                """
            )
            active, idle, current = (int(value or 0) for value in cursor.fetchone())

        usable_connections = max_connections - superuser_reserved
        declared_total = api_budget + background_budget + operational_reserve
        healthy = declared_total <= usable_connections
        payload = {
            "ok": healthy,
            "profile": os.getenv("LOCAL_SERVER_PROFILE", "development"),
            "postgres": {
                "max_connections": max_connections,
                "superuser_reserved_connections": superuser_reserved,
                "usable_connections": usable_connections,
                "current": current,
                "active": active,
                "idle": idle,
            },
            "budget": {
                "api": api_budget,
                "background": background_budget,
                "operational_reserve": operational_reserve,
                "declared_total": declared_total,
                "headroom": usable_connections - declared_total,
            },
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
        if options["strict"] and not healthy:
            raise CommandError("El presupuesto de conexiones excede la capacidad util de PostgreSQL.")
