from __future__ import annotations

import socket
import struct
from pathlib import Path

from django.conf import settings
from rest_framework.exceptions import ValidationError

EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
BLOCKED_SUFFIXES = {".apk", ".bat", ".cmd", ".com", ".dll", ".exe", ".js", ".msi", ".ps1", ".scr"}


def scan_document(*, content: bytes, filename: str) -> str:
    backend = str(getattr(settings, "DOCUMENTS_SCANNER_BACKEND", "basic") or "basic").lower()
    if backend == "clamav":
        _scan_with_clamav(content)
        return "clamav"
    if EICAR_MARKER in content or Path(filename).suffix.lower() in BLOCKED_SUFFIXES:
        raise ValidationError({"file": "El archivo fue rechazado por la politica de seguridad."})
    return "basic-policy-v1"


def _scan_with_clamav(content: bytes) -> None:
    host = str(getattr(settings, "DOCUMENTS_CLAMAV_HOST", "") or "").strip()
    port = int(getattr(settings, "DOCUMENTS_CLAMAV_PORT", 3310))
    if not host:
        raise ValidationError({"file": "ClamAV esta habilitado pero no configurado."})
    with socket.create_connection((host, port), timeout=10) as client:
        client.sendall(b"zINSTREAM\0")
        for offset in range(0, len(content), 65536):
            chunk = content[offset : offset + 65536]
            client.sendall(struct.pack(">I", len(chunk)) + chunk)
        client.sendall(struct.pack(">I", 0))
        response = client.recv(4096).decode("utf-8", errors="replace")
    if " FOUND" in response:
        raise ValidationError({"file": "El antivirus detecto contenido malicioso."})
    if " OK" not in response:
        raise ValidationError({"file": "El antivirus no pudo validar el archivo."})
