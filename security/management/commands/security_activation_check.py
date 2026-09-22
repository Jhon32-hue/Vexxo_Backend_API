import json
import os
import socket

from django.conf import settings
from django.core.management.base import BaseCommand

from integrations.open_banking.provider_catalog import list_providers
from security.encryption import encryption_status


def _clamav_status() -> dict:
    if settings.DOCUMENTS_SCANNER_BACKEND != "clamav":
        return {"enabled": False, "reachable": False}
    try:
        with socket.create_connection((settings.DOCUMENTS_CLAMAV_HOST, settings.DOCUMENTS_CLAMAV_PORT), timeout=3) as client:
            client.sendall(b"zPING\0")
            reachable = b"PONG" in client.recv(64)
    except OSError:
        reachable = False
    return {"enabled": True, "reachable": reachable}


class Command(BaseCommand):
    help = "Comprueba activacion de controles externos sin imprimir credenciales."

    def handle(self, *args, **options):
        payload = {
            "keyring": encryption_status(),
            "clamav": _clamav_status(),
            "play_integrity": {
                "configured": bool(settings.PLAY_INTEGRITY_CLOUD_PROJECT_NUMBER and settings.PLAY_INTEGRITY_SERVICE_ACCOUNT_JSON and settings.PLAY_INTEGRITY_PACKAGE_NAMES),
            },
            "app_attest": {
                "configured": bool(settings.APPLE_APP_ATTEST_APP_ID and settings.APPLE_APP_ATTEST_ROOT_CA_PEM),
                "environment": settings.APPLE_APP_ATTEST_ENVIRONMENT,
            },
            "open_banking": list_providers(),
            "payments": {
                "wompi_configured": all(bool(os.getenv(name, "").strip()) for name in ("WOMPI_PRIVATE_KEY", "WOMPI_INTEGRITY_SECRET", "WOMPI_EVENTS_SECRET")),
            },
        }
        self.stdout.write(json.dumps(payload, indent=2))
